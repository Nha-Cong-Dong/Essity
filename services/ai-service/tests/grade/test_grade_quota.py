"""T2.11: grading stops at the hard cap with a stable code, and the run is closed with it."""

import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_service.api.grade import get_audit_sessions, get_llm_client
from ai_service.llm.client import LlmClient
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import LlmRequest
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from tests.grade.helpers import grade_body
from tests.grade.test_grade_endpoint import BAD, GOOD, MODEL, Scripted, runs_of


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


class CapAfter:
    """A guard that lets `allowed` calls through, then refuses at the hard cap."""

    def __init__(self, allowed: int) -> None:
        self.allowed = allowed

    def reserve(self, request: LlmRequest, estimate: Decimal) -> uuid.UUID | None:
        if self.allowed <= 0:
            raise QuotaExceededError(hard=True, window="day")
        self.allowed -= 1
        return None

    def release(self, reservation_id: uuid.UUID, session: Session | None = None) -> None:
        raise AssertionError("no reservation was made")

    def hold(self, reservation_id: uuid.UUID) -> None:
        raise AssertionError("no reservation was made")


def client_with_cap(allowed: int, adapter: Scripted, sessions: sessionmaker[Session]) -> TestClient:
    app: FastAPI = create_app()
    app.dependency_overrides[get_audit_sessions] = lambda: sessions
    llm = LlmClient(adapter, sessions, models={"grade": MODEL}, quota_guard=CapAfter(allowed))
    app.dependency_overrides[get_llm_client] = lambda: llm
    return TestClient(app, headers={SERVICE_TOKEN_HEADER: "test-service-token-0123456789abcdef"})


def test_t211_hard_cap_answers_429_with_a_stable_code_and_no_numbers(
    engine: Engine, sessions: sessionmaker[Session]
) -> None:
    body = grade_body()
    adapter = Scripted(GOOD)
    response = client_with_cap(0, adapter, sessions).post("/v1/grade", json=body)
    assert response.status_code == 429
    assert response.json() == {"code": "quota_hard_cap"}
    assert adapter.requests == []


def test_t211_hard_cap_closes_the_run_with_its_code(
    engine: Engine, sessions: sessionmaker[Session]
) -> None:
    # Red when: the error falls into `except Exception` and the run reads internal_error.
    body = grade_body()
    client_with_cap(0, Scripted(GOOD), sessions).post("/v1/grade", json=body)
    [run] = runs_of(engine, body["user_id"])
    assert (run.status, run.error_code) == ("failed", "quota_hard_cap")


def test_t211_cap_reached_between_the_two_attempts_is_quota_not_grade_invalid(
    engine: Engine, sessions: sessionmaker[Session]
) -> None:
    body = grade_body()
    adapter = Scripted(BAD, GOOD)
    response = client_with_cap(1, adapter, sessions).post("/v1/grade", json=body)
    assert (response.status_code, response.json()) == (429, {"code": "quota_hard_cap"})
    assert len(adapter.requests) == 1
    [run] = runs_of(engine, body["user_id"])
    assert run.error_code == "quota_hard_cap"
