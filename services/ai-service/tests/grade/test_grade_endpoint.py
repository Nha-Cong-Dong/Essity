"""T2.12-b: POST /v1/grade over HTTP, on the real test database.

The model is a scripted adapter (or the real SDK on a fake API); llm_call and pipeline_run rows
are committed for real and read back through a connection of their own.
"""

import io
import json
import logging
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.api.grade import MAX_BODY_BYTES, get_audit_sessions, get_llm_client
from ai_service.db.models import LlmCall, PipelineRun
from ai_service.llm.client import LlmClient
from ai_service.llm.types import AdapterResult, LlmRequest, ProviderError, ProviderName
from ai_service.logging import configure_logging
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from ai_service.tasks.grade import load_prompt
from tests.grade.helpers import anchor, grade_body, unit
from tests.llm.helpers import NoQuota

MODEL = "claude-haiku-5-5"
GOOD = json.dumps(
    {
        "units": [{"unit": "U1", "verdict": "correct"}],
        "missing": [],
        "anchors_used": ["U1.A1"],
        "understanding": 3,
    }
)
BAD = '{"units": [], "missing": [], "anchors_used": [], "understanding": null, "raw-output": 1}'


class Scripted:
    """Answers each call with the next scripted text, or raises the scripted error."""

    provider: ProviderName = "anthropic"
    fixed_model: str | None = None
    params: dict[str, Any] = {}

    def __init__(self, *results: str | Exception) -> None:
        self.results = list(results)
        self.requests: list[LlmRequest] = []
        self.timeouts: list[float] = []

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        self.requests.append(request)
        self.timeouts.append(timeout)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return AdapterResult(
            text=result, input_tokens=100, output_tokens=20, stop_reason="end_turn"
        )


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def app(sessions: sessionmaker[Session]) -> Iterator[FastAPI]:
    app = create_app()
    app.dependency_overrides[get_audit_sessions] = lambda: sessions
    yield app


def client_with(app: FastAPI, adapter: Any, sessions: sessionmaker[Session]) -> TestClient:
    llm = LlmClient(adapter, sessions, models={"grade": MODEL}, quota_guard=NoQuota())
    app.dependency_overrides[get_llm_client] = lambda: llm
    return TestClient(app, headers={SERVICE_TOKEN_HEADER: "test-service-token-0123456789abcdef"})


def runs_of(engine: Engine, user_id: str) -> list[PipelineRun]:
    with Session(engine) as session:
        query = select(PipelineRun).where(PipelineRun.user_id == uuid.UUID(user_id))
        return list(session.scalars(query))


def calls_of(engine: Engine, user_id: str) -> list[LlmCall]:
    with Session(engine) as session:
        query = (
            select(LlmCall).where(LlmCall.user_id == uuid.UUID(user_id)).order_by(LlmCall.attempt)
        )
        return list(session.scalars(query))


# --- Success ---------------------------------------------------------------------------------


def test_t212_grade_returns_the_contract(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    body = grade_body()
    response = client_with(app, Scripted(GOOD), sessions).post("/v1/grade", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    [run] = runs_of(engine, body["user_id"])
    [call] = calls_of(engine, body["user_id"])
    assert data == {
        "provider": "anthropic",
        "model": MODEL,
        "prompt_version": "v1",
        "run_id": str(run.id),
        "llm_call_id": str(call.id),
        "overall": "correct",
        "understanding": 3,
        "missing": [],
        "units": [{"unit_id": body["units"][0]["unit_id"], "verdict": "correct"}],
        "anchors_used": [body["units"][0]["anchors"][0]["anchor_id"]],
    }


def test_t212_pipeline_run_is_written_and_closed(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    body = grade_body()
    client_with(app, Scripted(GOOD), sessions).post("/v1/grade", json=body)
    [run] = runs_of(engine, body["user_id"])
    assert (run.subject_id, run.attempt_id) == (
        uuid.UUID(body["subject_id"]),
        uuid.UUID(body["attempt_id"]),
    )
    assert (run.task, run.prompt_version, run.status, run.error_code) == (
        "grade",
        "v1",
        "succeeded",
        None,
    )
    assert run.prompt_sha256 == load_prompt().sha256
    assert run.finished_at is not None


def test_us05_ac9_verdict_per_unit(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # Red when: the result is one verdict for the whole answer, not one per unit (AC9).
    units = [unit("Flow control"), unit("Độ trễ của UDP")]
    output = json.dumps(
        {
            "units": [{"unit": "U2", "verdict": "incorrect"}, {"unit": "U1", "verdict": "correct"}],
            "missing": ["Chưa nói về độ trễ của UDP"],
            "anchors_used": ["U1.A1"],
            "understanding": 1,
        },
        ensure_ascii=False,
    )
    body = grade_body(units=units)
    data = client_with(app, Scripted(output), sessions).post("/v1/grade", json=body).json()
    assert data["units"] == [
        {"unit_id": units[0]["unit_id"], "verdict": "correct"},
        {"unit_id": units[1]["unit_id"], "verdict": "incorrect"},
    ]
    assert (data["overall"], data["understanding"]) == ("partial", 1)
    assert data["missing"] == ["Chưa nói về độ trễ của UDP"]


def test_us05_ac8_request_carries_all_unit_quotes(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # Red when: the audit row does not show which sources were read (AC8: the log keeps them).
    units = [unit("A", anchor("nguồn một"), anchor("nguồn hai")), unit("B", anchor("nguồn ba"))]
    output = json.dumps(
        {
            "units": [{"unit": "U1", "verdict": "correct"}, {"unit": "U2", "verdict": "correct"}],
            "missing": [],
            "anchors_used": ["U1.A1", "U2.A1"],
            "understanding": 1,
        }
    )
    body = grade_body(units=units)
    client_with(app, Scripted(output), sessions).post("/v1/grade", json=body)
    [call] = calls_of(engine, body["user_id"])
    sent = call.input["messages"][0]["content"]
    for label in ("U1.A1", "U1.A2", "U2.A1"):
        assert f'anchor="{label}"' in sent
    for text in ("nguồn một", "nguồn hai", "nguồn ba"):
        assert text in sent


def test_b2_the_model_gets_at_most_nine_seconds(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    adapter = Scripted(GOOD)
    client_with(app, adapter, sessions).post("/v1/grade", json=grade_body())
    assert 8.0 < adapter.timeouts[0] <= 9.0


# --- Empty answer (🟠6) -----------------------------------------------------------------------


@pytest.mark.parametrize("answer", ["", "  \n "])
def test_o6_empty_answer_is_incorrect_without_a_model(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine, answer: str
) -> None:
    # Red when: an empty answer is sent to the model (paid, and it may grade it "partial").
    adapter = Scripted()
    units = [unit("Bắt tay"), unit("Flow control")]
    body = grade_body(answer=answer, units=units)
    response = client_with(app, adapter, sessions).post("/v1/grade", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert adapter.requests == []
    assert calls_of(engine, body["user_id"]) == []
    assert [u["verdict"] for u in data["units"]] == ["incorrect", "incorrect"]
    assert (data["overall"], data["understanding"], data["anchors_used"]) == ("incorrect", None, [])
    assert data["missing"] == ["Bắt tay", "Flow control"]
    assert (data["provider"], data["model"], data["llm_call_id"]) == ("none", None, None)
    [run] = runs_of(engine, body["user_id"])
    assert run.status == "succeeded"


# --- R03: one retry, then 502 ------------------------------------------------------------------


def test_r03_retry_once_then_502(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # Red when: a bad output is retried more than once (cost) or not at all, or a call of the
    # two is not written.
    adapter = Scripted(BAD, BAD)
    body = grade_body()
    response = client_with(app, adapter, sessions).post("/v1/grade", json=body)
    assert (response.status_code, response.json()) == (502, {"code": "grade_invalid"})
    calls = calls_of(engine, body["user_id"])
    assert [c.attempt for c in calls] == [1, 2]
    assert all(c.output == BAD for c in calls)
    [run] = runs_of(engine, body["user_id"])
    assert (run.status, run.error_code) == ("failed", "grade_invalid")


def test_r03_retry_once_then_success(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    adapter = Scripted(BAD, GOOD)
    body = grade_body()
    response = client_with(app, adapter, sessions).post("/v1/grade", json=body)
    assert response.status_code == 200
    calls = calls_of(engine, body["user_id"])
    assert [c.attempt for c in calls] == [1, 2]
    assert response.json()["llm_call_id"] == str(calls[1].id)
    assert [r.attempt for r in adapter.requests] == [1, 2]


NO_SOURCE = json.dumps(
    {
        "units": [{"unit": "U1", "verdict": "correct"}],
        "missing": [],
        "anchors_used": [],
        "understanding": 3,
    }
)


def test_r03_3b_right_grade_without_a_source_is_retried_then_502(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # Review 🟡1: a "correct" that names no source is a violation like the others.
    body = grade_body()
    response = client_with(app, Scripted(NO_SOURCE, NO_SOURCE), sessions).post(
        "/v1/grade", json=body
    )
    assert (response.status_code, response.json()) == (502, {"code": "grade_invalid"})
    assert [c.attempt for c in calls_of(engine, body["user_id"])] == [1, 2]


def test_r03_3b_retry_with_a_source_passes(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    body = grade_body()
    response = client_with(app, Scripted(NO_SOURCE, GOOD), sessions).post("/v1/grade", json=body)
    assert response.status_code == 200
    assert response.json()["anchors_used"] == [body["units"][0]["anchors"][0]["anchor_id"]]


def test_o4_bad_output_then_provider_error_keeps_every_row(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # Review 🟢1 (replaces the rollback test of T2.10): the request fails, and the run and both
    # calls are still there, read through a connection of their own.
    adapter = Scripted(BAD, ProviderError("provider_error"))
    body = grade_body()
    response = client_with(app, adapter, sessions).post("/v1/grade", json=body)
    assert (response.status_code, response.json()) == (502, {"code": "llm_unavailable"})
    calls = calls_of(engine, body["user_id"])
    assert [(c.attempt, c.error_code) for c in calls] == [(1, None), (2, "provider_error")]
    [run] = runs_of(engine, body["user_id"])
    assert (run.status, run.error_code) == ("failed", "llm_unavailable")
    assert {c.pipeline_run_id for c in calls} == {run.id}


def test_t212_provider_error_is_not_retried_here(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # core retries llm_unavailable (T2.13); retrying here as well would multiply the calls.
    adapter = Scripted(ProviderError("timeout"))
    body = grade_body()
    response = client_with(app, adapter, sessions).post("/v1/grade", json=body)
    assert (response.status_code, response.json()) == (502, {"code": "llm_unavailable"})
    assert len(calls_of(engine, body["user_id"])) == 1


def test_t212_error_body_does_not_echo_the_output(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    response = client_with(app, Scripted(BAD, BAD), sessions).post("/v1/grade", json=grade_body())
    assert "raw-output" not in response.text


# --- Disabled, audit down, bad requests --------------------------------------------------------


def test_t210_disabled_grading_answers_503_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # B6: no call, so no llm_call row; the deploy without a key says so instead of failing.
    monkeypatch.setenv("AI_LLM_PROVIDER", "disabled")
    app = create_app()
    app.dependency_overrides[get_audit_sessions] = lambda: sessions
    body = grade_body()
    headers = {SERVICE_TOKEN_HEADER: "test-service-token-0123456789abcdef"}
    with TestClient(app, headers=headers) as client:
        response = client.post("/v1/grade", json=body)
    assert (response.status_code, response.json()) == (503, {"code": "grading_disabled"})
    assert runs_of(engine, body["user_id"]) == []


def test_d_audit_down_is_503_before_any_money_is_spent(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # 🟡d: pipeline_run is written before the model is called; if it cannot be, no call.
    def broken() -> Session:
        session = sessions()
        session.commit = _database_down  # type: ignore[method-assign]
        return session

    adapter = Scripted(GOOD)
    client = client_with(app, adapter, sessions)
    app.dependency_overrides[get_audit_sessions] = lambda: broken
    response = client.post("/v1/grade", json=grade_body())
    assert (response.status_code, response.json()) == (503, {"code": "audit_unavailable"})
    assert adapter.requests == []


def _database_down() -> None:
    raise OSError("database is down")


def test_b3_llm_call_write_failure_is_503(app: FastAPI, sessions: sessionmaker[Session]) -> None:
    # The run is written, the model answers, its row cannot be written: no grade (B3).
    commits = {"n": 0}

    def second_commit_fails() -> Session:
        session = sessions()
        real_commit = session.commit

        def commit() -> None:
            commits["n"] += 1
            if commits["n"] == 2:
                raise OSError("database is down")
            real_commit()

        session.commit = commit  # type: ignore[method-assign]
        return session

    llm = LlmClient(
        Scripted(GOOD), second_commit_fails, models={"grade": MODEL}, quota_guard=NoQuota()
    )
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_audit_sessions] = lambda: second_commit_fails
    client = TestClient(app, headers={SERVICE_TOKEN_HEADER: "test-service-token-0123456789abcdef"})
    response = client.post("/v1/grade", json=grade_body())
    assert (response.status_code, response.json()) == (503, {"code": "audit_unavailable"})


def test_t212_invalid_request_is_422_without_echoing_input(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # 🟠9: a stable code, and none of the request's text (core must not log answers by accident).
    body = grade_body(answer="secret-answer-text" * 300)
    response = client_with(app, Scripted(), sessions).post("/v1/grade", json=body)
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "invalid_request"
    assert "secret-answer-text" not in response.text
    assert all(set(error) <= {"loc", "type", "msg"} for error in data["errors"])


@pytest.mark.parametrize("missing", ["user_id", "subject_id"])
def test_t210_grade_without_user_id_is_422(
    app: FastAPI, sessions: sessionmaker[Session], missing: str
) -> None:
    body = grade_body()
    del body[missing]
    response = client_with(app, Scripted(), sessions).post("/v1/grade", json=body)
    assert (response.status_code, response.json()["code"]) == (422, "invalid_request")


def test_e_duplicate_ids_are_422(app: FastAPI, sessions: sessionmaker[Session]) -> None:
    first = unit()
    body = grade_body(units=[first, {**unit(), "unit_id": first["unit_id"]}])
    response = client_with(app, Scripted(), sessions).post("/v1/grade", json=body)
    assert response.status_code == 422


def test_g6_oversized_body_is_413(app: FastAPI, sessions: sessionmaker[Session]) -> None:
    adapter = Scripted()
    payload = json.dumps(grade_body(padding="x" * MAX_BODY_BYTES))
    client = client_with(app, adapter, sessions)
    response = client.post(
        "/v1/grade", content=payload, headers={"Content-Type": "application/json"}
    )
    assert (response.status_code, response.json()) == (413, {"code": "request_too_large"})
    assert adapter.requests == []


def test_t212_grade_needs_the_service_token(app: FastAPI) -> None:
    assert TestClient(app).post("/v1/grade", json=grade_body()).status_code == 401


# --- Logs ------------------------------------------------------------------------------------


@pytest.fixture
def log_output() -> Iterator[io.StringIO]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("ai-service", "DEBUG", stream=buffer)
    yield buffer
    root.handlers, root.level = saved


def test_t212_log_lines_name_the_user(
    app: FastAPI, sessions: sessionmaker[Session], log_output: io.StringIO
) -> None:
    body = grade_body()
    client_with(app, Scripted(GOOD), sessions).post("/v1/grade", json=body)
    lines = [json.loads(line) for line in log_output.getvalue().splitlines()]
    access = [line for line in lines if line["logger"] == "ai_service.access"]
    assert access and access[0]["user_id"] == body["user_id"]
    llm = [line for line in lines if line["message"] == "llm call"]
    assert llm and llm[0]["provider"] == "anthropic" and "llm_call_id" in llm[0]


def test_t212_deadline_is_measured_from_the_request(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    class Slow(Scripted):
        def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
            time.sleep(0.2)
            return super().complete(request, model=model, timeout=timeout)

    adapter = Slow(BAD, GOOD)
    client_with(app, adapter, sessions).post("/v1/grade", json=grade_body())
    assert adapter.timeouts[1] <= adapter.timeouts[0] - 0.2
