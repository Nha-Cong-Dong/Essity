"""T9.6b (US-17 AC1, AC4, AC6, AC8, ADR-0013): POST /v1/generate-like over HTTP on the real test
database. The model is scripted; nothing here calls a paid model."""

import json
import logging
import uuid
from collections.abc import Iterator
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
from ai_service.llm.types import AdapterResult, LlmRequest, ProviderError, ProviderName
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from ai_service.tasks.like_run import fake_generate_like, fake_judge_questions
from tests.generate_like import helpers
from tests.generate_like.helpers import C1, gen, judged, verdict
from tests.llm.helpers import NoQuota


def cand(n: int = 1, **kw: Any) -> dict[str, Any]:
    return helpers.cand(n, **{"cards": ["C1"], **kw})


MODEL = "claude-haiku-5-5"
TOKEN = "test-service-token-0123456789abcdef"
URL = "/v1/generate-like"


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


def body(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "user_id": str(uuid.uuid4()),
        "subject_id": str(uuid.uuid4()),
        "type_name": "Explain",
        "samples": [{"prompt": "Explain how the cell membrane controls entry."}],
        "cards": [{"card_id": str(C1), "text": "Mitochondria produce ATP."}],
    }
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _no_like_rows_left(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as connection:
        for table in ("llm_call", "pipeline_run"):
            connection.execute(
                text(f"DELETE FROM {table} WHERE task IN ('generate_like', 'judge_questions')")  # noqa: S608
            )


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def app(sessions: sessionmaker[Session]) -> Iterator[FastAPI]:
    app = create_app()
    app.dependency_overrides[get_audit_sessions] = lambda: sessions
    yield app


def client_with(app: FastAPI, adapter: Scripted, sessions: sessionmaker[Session]) -> TestClient:
    models = {"generate_like": MODEL, "judge_questions": MODEL}
    llm = LlmClient(adapter, sessions, models=models, quota_guard=NoQuota())
    app.dependency_overrides[get_llm_client] = lambda: llm
    return TestClient(app, headers={SERVICE_TOKEN_HEADER: TOKEN})


def calls_of(engine: Engine, user_id: str) -> list[LlmCall]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(LlmCall)
                .where(LlmCall.user_id == uuid.UUID(user_id))
                .order_by(LlmCall.created_at)
            )
        )


def test_one_click_is_two_audited_calls_and_one_run(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # US-17 AC4, AC6. Red when: more than generate + judge is called, or an audit row is missing.
    b = body()
    two = cand(2, prompt="Why does a cell need ATP when it divides and grows quickly?")
    adapter = Scripted(gen(cand(1), two), judged(verdict("Q1"), verdict("Q2", j3=False)))
    response = client_with(app, adapter, sessions).post(URL, json=b)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ok" and len(data["kept"]) == 1
    assert [d["reason"] for d in data["dropped"]] == ["judge_j3_generic"]
    assert len(adapter.requests) == 2
    assert [c.task for c in calls_of(engine, b["user_id"])] == ["generate_like", "judge_questions"]
    with Session(engine) as session:
        [run] = session.scalars(
            select(PipelineRun).where(PipelineRun.user_id == uuid.UUID(b["user_id"]))
        )
    assert (run.task, run.status, str(run.id)) == ("generate_like", "succeeded", data["run_id"])


def test_prompt_carries_no_ids(app: FastAPI, sessions: sessionmaker[Session]) -> None:
    # US-17 section 7. Red when: the user, subject or card id reaches the model.
    b = body()
    adapter = Scripted(gen(cand(1)), judged(verdict("Q1")))
    client_with(app, adapter, sessions).post(URL, json=b)
    sent = "".join(r.system + r.user for r in adapter.requests)
    assert b["user_id"] not in sent and b["subject_id"] not in sent and str(C1) not in sent


def test_no_card_means_no_call(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # US-17 AC2. Red when: a call is paid for a request with nothing studied to ask about.
    b = body(cards=[])
    adapter = Scripted()
    data = client_with(app, adapter, sessions).post(URL, json=b).json()
    assert (data["status"], data["failure"]) == ("empty", "no_cards")
    assert adapter.requests == [] and calls_of(engine, b["user_id"]) == []


def test_pending_ai_is_a_200_and_never_retried(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # US-17 AC6, AC8. Red when: a model outage is an error status or the call is repeated.
    adapter = Scripted(ProviderError("timeout"))
    response = client_with(app, adapter, sessions).post(URL, json=body())
    assert (response.status_code, response.json()["status"]) == (200, "pending_ai")
    assert len(adapter.requests) == 1


def test_no_candidate_passing_is_empty_without_a_second_generation(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # US-17 AC6. Red when: nothing passing triggers another generation.
    adapter = Scripted(gen(cand(1)), judged(verdict("Q1", j4=False)))
    data = client_with(app, adapter, sessions).post(URL, json=body()).json()
    assert data["status"] == "empty" and data["kept"] == []
    assert len(adapter.requests) == 2


def test_replies_and_logs_never_carry_model_text(
    app: FastAPI, sessions: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    # ADR-0013. Red when: a malformed reply's text is in the response or a log.
    secret = "SECRET-MODEL-TEXT"
    with caplog.at_level(logging.DEBUG):
        response = client_with(app, Scripted(json.dumps({"candidates": secret})), sessions).post(
            URL, json=body(samples=[{"prompt": "SECRET-SAMPLE-1"}])
        )
    assert response.json()["failure"] == "generation_malformed"
    assert secret not in response.text and secret not in caplog.text
    assert "SECRET-SAMPLE-1" not in caplog.text


def test_duplicate_card_is_422_without_text(app: FastAPI, sessions: sessionmaker[Session]) -> None:
    # Red when: a request the core refuses becomes a 500.
    card = {"card_id": str(C1), "text": "SECRET-CARD"}
    response = client_with(app, Scripted(), sessions).post(URL, json=body(cards=[card, card]))
    assert response.status_code == 422 and "SECRET-CARD" not in response.text


def test_service_token_is_required(app: FastAPI, sessions: sessionmaker[Session]) -> None:
    # ADR-0001. Red when: the route answers without the token.
    client = client_with(app, Scripted(), sessions)
    client.headers.pop(SERVICE_TOKEN_HEADER)
    assert client.post(URL, json=body()).status_code in (401, 403)


def test_fake_provider_round_trip_passes_the_schema(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # Local mode (AI_LLM_PROVIDER=fake). Red when: the fake responders break the output schema.
    adapter = FakeAdapter(
        {"generate_like": fake_generate_like, "judge_questions": fake_judge_questions}
    )
    llm = LlmClient(adapter, sessions, models={}, quota_guard=NoQuota())
    app.dependency_overrides[get_llm_client] = lambda: llm
    client = TestClient(app, headers={SERVICE_TOKEN_HEADER: TOKEN})
    data = client.post(URL, json=body()).json()
    assert data["status"] == "ok" and len(data["kept"]) == 5
