"""T7.9 (US-02b AC11, ADR-0013): POST /v1/review-question on the real test database. The model is
scripted; nothing here calls a paid model. LLM calls are counted: one per request."""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.api.grade import get_audit_sessions, get_llm_client
from ai_service.db.models import PipelineRun
from ai_service.llm.client import LlmClient
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import ProviderError
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from tests.grade_practice.test_endpoint import MODEL, TOKEN, Scripted
from tests.llm.helpers import NoQuota

URL = "/v1/review-question"
GOOD = json.dumps(
    {
        "questions": [
            {
                "unit": "U1",
                "prompt": "Explain the handshake?",
                "reference_answer": "SYN, SYN-ACK, ACK.",
                "rubric": "Three steps. Partial if one missing.",
            }
        ]
    }
)


def body(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "user_id": str(uuid.uuid4()),
        "subject_id": str(uuid.uuid4()),
        "unit_id": str(uuid.uuid4()),
        "title": "TCP handshake",
        "summary": "Three steps open a connection.",
        "quotes": ["Client sends SYN."],
    }
    base.update(kw)
    return base


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def app(sessions: sessionmaker[Session]) -> Iterator[FastAPI]:
    app = create_app()
    app.dependency_overrides[get_audit_sessions] = lambda: sessions
    yield app


def client(
    app: FastAPI, adapter: Scripted, sessions: sessionmaker[Session], quota: Any = None
) -> TestClient:
    llm = LlmClient(
        adapter, sessions, models={"generate_questions": MODEL}, quota_guard=quota or NoQuota()
    )
    app.dependency_overrides[get_llm_client] = lambda: llm
    return TestClient(app, headers={SERVICE_TOKEN_HEADER: TOKEN})


def test_ac11_one_call_returns_question_rubric_and_answer(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # US-02b AC11. Red when: more than one model call, the rubric or answer is not returned (it is
    # stored with the question, so grading never resends anchors), or no pipeline_run is audited.
    payload = body()
    adapter = Scripted(GOOD)
    response = client(app, adapter, sessions).post(URL, json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ok"
    assert data["prompt"] == "Explain the handshake?"
    assert data["reference_answer"] == "SYN, SYN-ACK, ACK."
    assert data["rubric"].startswith("Three steps")
    assert len(adapter.requests) == 1
    with Session(engine) as session:
        [run] = session.scalars(
            select(PipelineRun).where(PipelineRun.user_id == uuid.UUID(payload["user_id"]))
        )
    assert (run.task, run.status, str(run.id)) == (
        "generate_questions",
        "succeeded",
        data["run_id"],
    )


def test_ac11_prompt_has_the_card_and_no_ids(app: FastAPI, sessions: sessionmaker[Session]) -> None:
    # Red when: an id reaches the model (ADR-0013: labels only).
    payload = body()
    adapter = Scripted(GOOD)
    client(app, adapter, sessions).post(URL, json=payload)
    [request] = adapter.requests
    text = request.system + request.user
    assert "TCP handshake" in text and "Client sends SYN" in text
    for key in ("user_id", "subject_id", "unit_id"):
        assert payload[key] not in text


class CappedQuota:
    """The account is over its cap: every reservation is refused."""

    def reserve(self, request: Any, estimate: Any) -> Any:
        raise QuotaExceededError(hard=False, window="day")


def test_ac11_cap_reached_is_pending_ai_and_calls_no_model(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # Red when: the cap becomes an error (core would show one) or the model is called anyway.
    adapter = Scripted()
    response = client(app, adapter, sessions, CappedQuota()).post(URL, json=body())
    assert response.status_code == 200
    assert response.json()["status"] == "pending_ai"
    assert adapter.requests == []


def test_ac11_provider_down_is_pending_ai_not_an_error(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # Red when: model trouble becomes a 5xx (core would then retry as an error) instead of 200
    # pending_ai (the card enters review without a question, no error).
    adapter = Scripted(ProviderError("timeout"))
    response = client(app, adapter, sessions).post(URL, json=body())
    assert response.status_code == 200
    data = response.json()
    assert (data["status"], data["prompt"]) == ("pending_ai", None)


def test_ac11_broken_output_is_failed_with_a_rule_name_only(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    adapter = Scripted("not json", "not json")
    response = client(app, adapter, sessions).post(URL, json=body())
    data = response.json()
    assert (data["status"], data["failure"]) == ("failed", "output_invalid")
    assert "not json" not in response.text
    assert len(adapter.requests) == 2  # ATTEMPTS: the core retries once


def test_ac11_rejects_a_missing_token(app: FastAPI) -> None:
    assert TestClient(app).post(URL, json=body()).status_code in (401, 403)
