"""T8.1b (US-14 AC1-AC3, AC9, ADR-0013): POST /v1/parse-question-bank over HTTP on the test
database. The model is scripted or the fake provider; nothing here calls a paid model."""

import json
import logging
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from ai_service.api.grade import get_audit_sessions, get_llm_client
from ai_service.db.models import LlmCall, PipelineRun
from ai_service.llm.client import LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import AdapterResult, LlmRequest, ProviderName
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from ai_service.tasks.bank_run import fake_parse_question_bank
from tests.llm.helpers import NoQuota

MODEL = "claude-haiku-5-5"
TOKEN = "test-service-token-0123456789abcdef"
URL = "/v1/parse-question-bank"
PAGE = (
    "Câu 1. TCP mở kết nối như thế nào?\n"
    "Đáp án: Bằng bắt tay ba bước.\n"
    "Câu 2. UDP có bảo đảm không?"
)


class Scripted:
    provider: ProviderName = "anthropic"
    fixed_model: str | None = None
    params: dict[str, Any] = {}

    def __init__(self, *results: str | Exception) -> None:
        self.results = list(results)
        self.requests: list[LlmRequest] = []

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        self.requests.append(request)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return AdapterResult(text=result, input_tokens=100, output_tokens=20, stop_reason="end")


class OutOfQuota(NoQuota):
    def reserve(self, request: LlmRequest, estimate: Decimal) -> uuid.UUID | None:
        raise QuotaExceededError(hard=False, window="day")


def body(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "user_id": str(uuid.uuid4()),
        "subject_id": str(uuid.uuid4()),
        "pages": [{"text": PAGE, "needs_vision": False}],
        "existing_types": [],
        "sections": [{"id": "sec-a", "title": "Giao thức TCP"}, {"id": "sec-b", "title": "UDP"}],
    }
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _no_rows_left(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as connection:
        for table in ("llm_call", "pipeline_run"):
            connection.execute(text(f"DELETE FROM {table} WHERE task = 'parse_question_bank'"))  # noqa: S608


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def app(sessions: sessionmaker[Session]) -> Iterator[FastAPI]:
    app = create_app()
    app.dependency_overrides[get_audit_sessions] = lambda: sessions
    yield app


def client_with(
    app: FastAPI, adapter: Any, sessions: sessionmaker[Session], quota: Any = None
) -> TestClient:
    llm = LlmClient(
        adapter,
        sessions,
        models={"parse_question_bank": MODEL},
        quota_guard=quota or NoQuota(),
    )
    app.dependency_overrides[get_llm_client] = lambda: llm
    return TestClient(app, headers={SERVICE_TOKEN_HEADER: TOKEN})


TYPES = json.dumps({"types": [{"name": "Giải thích", "questions": ["Q1", "Q2"]}]})
MAPS = json.dumps({"mappings": [{"question": "Q1", "sections": ["S1"]}]})


def test_numbered_bank_is_two_audited_calls_in_one_run(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # US-14 AC1-AC3. Red when: a numbered bank pays for a split call, more than types + sections
    # is called, or the questions are not batched.
    b = body()
    adapter = Scripted(TYPES, MAPS)
    response = client_with(app, adapter, sessions).post(URL, json=b)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ok" and len(adapter.requests) == 2
    q1, q2 = data["questions"]
    assert (q1["prompt"], q1["answer_text"]) == (
        "TCP mở kết nối như thế nào?",
        "Bằng bắt tay ba bước.",
    )
    assert (q1["type_name"], q1["section_ids"]) == ("Giải thích", ["sec-a"])
    assert (q2["answer_text"], q2["section_ids"]) == (None, [])
    assert data["unmapped"] == [2]
    with Session(engine) as session:
        [run] = session.scalars(
            select(PipelineRun).where(PipelineRun.user_id == uuid.UUID(b["user_id"]))
        )
        calls = session.scalars(select(LlmCall).where(LlmCall.user_id == uuid.UUID(b["user_id"])))
        assert {c.task for c in calls} == {"parse_question_bank"}
    assert (run.task, run.status, str(run.id)) == (
        "parse_question_bank",
        "succeeded",
        data["run_id"],
    )


def test_prompt_carries_no_ids(app: FastAPI, sessions: sessionmaker[Session]) -> None:
    # US-14 section 7. Red when: a user, subject or section id reaches the model.
    b = body()
    adapter = Scripted(TYPES, MAPS)
    client_with(app, adapter, sessions).post(URL, json=b)
    sent = "".join(r.system + r.user for r in adapter.requests)
    assert b["user_id"] not in sent and b["subject_id"] not in sent and "sec-a" not in sent


def test_quota_is_pending_ai_with_nothing_to_store(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # US-14 AC9. Red when: a run stopped by the quota returns questions to store, or the run is
    # left open.
    b = body()
    client = client_with(app, Scripted(), sessions, OutOfQuota())
    response = client.post(URL, json=b)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["status"], data["questions"]) == ("pending_ai", [])
    with Session(engine) as session:
        [run] = session.scalars(
            select(PipelineRun).where(PipelineRun.user_id == uuid.UUID(b["user_id"]))
        )
    assert run.status == "failed" and run.error_code == "quota_or_unavailable"


def test_broken_model_output_keeps_what_was_checked(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # US-14 AC1. Red when: a bad types reply loses the questions or is not partial.
    adapter = Scripted("nope", "nope", MAPS)
    data = client_with(app, adapter, sessions).post(URL, json=body()).json()
    assert data["status"] == "partial" and len(data["questions"]) == 2
    assert data["questions"][0]["type_name"] is None
    assert "malformed_output" in data["reasons"]


def test_logs_never_hold_question_text(
    app: FastAPI, sessions: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    # ADR-0013. Red when: a question or answer reaches a log.
    caplog.set_level(logging.DEBUG)
    client_with(app, Scripted(TYPES, MAPS), sessions).post(URL, json=body())
    assert "bắt tay ba bước" not in caplog.text and "TCP mở kết nối" not in caplog.text


def test_fake_provider_completes_a_run_without_a_model(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # Local and CI use. Red when: AI_LLM_PROVIDER=fake cannot answer the types and sections steps.
    adapter = FakeAdapter({"parse_question_bank": fake_parse_question_bank})
    data = client_with(app, adapter, sessions).post(URL, json=body()).json()
    assert data["status"] == "ok" and len(data["questions"]) == 2
    assert all(q["type_name"] for q in data["questions"])


def test_unknown_field_and_no_token_are_refused(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # R03 layer 2. Red when: an extra field is accepted or the route is open without the token.
    client = client_with(app, Scripted(), sessions)
    assert client.post(URL, json=body(extra=1)).status_code == 422
    assert TestClient(app).post(URL, json=body()).status_code in (401, 403)
