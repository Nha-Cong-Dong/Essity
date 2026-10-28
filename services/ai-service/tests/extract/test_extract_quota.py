"""T4.10 x T2.11: extract_session goes through the LlmClient quota guard like grade."""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_service.api.grade import get_audit_sessions, get_llm_client
from ai_service.llm.client import LlmClient
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import LlmRequest
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from tests.extract.helpers import extract_body
from tests.extract.test_extract_endpoint import GOOD, MODEL, TOKEN, Scripted, runs_of


class AlwaysCapped:
    def reserve(self, request: LlmRequest, estimate: Decimal) -> uuid.UUID | None:
        raise QuotaExceededError(hard=True, window="day")

    def release(self, reservation_id: uuid.UUID, session: Session | None = None) -> None:
        raise AssertionError("no reservation was made")

    def hold(self, reservation_id: uuid.UUID) -> None:
        raise AssertionError("no reservation was made")


def test_t211_hard_cap_answers_429_and_closes_the_run_with_its_code(
    engine: Engine, sessions: sessionmaker[Session]
) -> None:
    # Red when: the error falls into `except Exception` (500, run reads internal_error).
    app = create_app()
    app.dependency_overrides[get_audit_sessions] = lambda: sessions
    adapter = Scripted(GOOD)
    llm = LlmClient(
        adapter, sessions, models={"extract_session": MODEL}, quota_guard=AlwaysCapped()
    )
    app.dependency_overrides[get_llm_client] = lambda: llm
    client = TestClient(app, headers={SERVICE_TOKEN_HEADER: TOKEN})
    body = extract_body()
    response = client.post("/v1/extract-session", json=body)
    assert (response.status_code, response.json()) == (429, {"code": "quota_hard_cap"})
    assert adapter.requests == []
    [run] = runs_of(engine, body["user_id"])
    assert (run.status, run.error_code) == ("failed", "quota_hard_cap")
