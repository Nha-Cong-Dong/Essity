"""Tester's edge cases for POST /v1/grade (PR B): size at the limits, malformed text, concurrency.

Same setup as test_grade_endpoint: a scripted model, the real test database, rows read back
through a connection of their own.
"""

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_service.api.grade import get_audit_sessions, get_llm_client
from ai_service.llm.client import LlmClient
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from tests.grade.helpers import anchor, grade_body, unit
from tests.grade.test_grade_endpoint import (
    GOOD,
    MODEL,
    Scripted,
    calls_of,
    client_with,
    runs_of,
)

HEADERS = {"Content-Type": "application/json"}


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def app(sessions: sessionmaker[Session]) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_audit_sessions] = lambda: sessions
    return app


def five_right(units: int) -> str:
    return json.dumps(
        {
            "units": [{"unit": f"U{i}", "verdict": "correct"} for i in range(1, units + 1)],
            "missing": [],
            "anchors_used": ["U1.A1"],
            "understanding": 3,
        }
    )


def largest_body(char: str) -> dict[str, Any]:
    """Every field at its limit: 5 units x 5 anchors, 12000 quote characters in all."""
    units = [unit(char * 200, *[anchor(char * 480) for _ in range(5)]) for _ in range(5)]
    question = {"text": char * 4000, "rubric": char * 4000, "reference_answer": char * 4000}
    return grade_body(answer=char * 4000, question=question, units=units)


def test_g6_largest_valid_request_in_vietnamese_escaped_as_ascii_is_not_refused(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # Red when: MAX_BODY_BYTES drops below what a full request costs. `json.dumps` escapes each
    # Vietnamese letter as \uXXXX (6 bytes), about 175 KB here: the plan's 64 KB would refuse it.
    payload = json.dumps(largest_body("ệ"))
    assert 64 * 1024 < len(payload) < 256 * 1024
    client = client_with(app, Scripted(five_right(5)), sessions)
    response = client.post("/v1/grade", content=payload, headers=HEADERS)
    assert response.status_code == 200, response.text[:200]


def test_g6_largest_valid_request_in_emoji_escaped_as_ascii_is_not_refused(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # Red when: the body limit is below the escaped size of a request inside the G6 limits.
    payload = json.dumps(largest_body("😀"))
    client = client_with(app, Scripted(five_right(5)), sessions)
    response = client.post("/v1/grade", content=payload, headers=HEADERS)
    assert response.status_code == 200, (response.status_code, response.text[:200])


@pytest.mark.parametrize(
    "field", ["answer", "quote_text", "title", "text", "rubric", "reference_answer"]
)
def test_t212_nul_character_in_text_is_not_an_audit_failure(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine, field: str
) -> None:
    # Red when: text with U+0000 reaches `llm_call.input` (JSONB refuses it) or `pipeline_run`:
    # the model has been paid for, then the learner gets 503 audit_unavailable on every retry.
    # Fixed by refusing it up front: 422 invalid_request, no run, no call.
    text = "TCP bắt tay\u0000 ba bước"
    question = {"text": "Câu hỏi", "rubric": "Thang", "reference_answer": "Bắt tay ba bước"}
    if field == "answer":
        body = grade_body(answer=text)
    elif field == "quote_text":
        body = grade_body(units=[unit("Mảnh", anchor(text))])
    elif field == "title":
        body = grade_body(units=[unit(text)])
    else:
        body = grade_body(question={**question, field: text})
    adapter = Scripted(GOOD)
    response = client_with(app, adapter, sessions).post("/v1/grade", json=body)
    assert (response.status_code, response.json()["code"]) == (422, "invalid_request")
    assert "bắt tay" not in response.text  # the input is not echoed back
    assert adapter.requests == []  # refused before any money was spent
    assert calls_of(engine, body["user_id"]) == []


def test_t212_lone_surrogate_in_the_answer_is_not_an_audit_failure(
    app: FastAPI, sessions: sessionmaker[Session]
) -> None:
    # Red when: a lone surrogate (valid in a JSON string, impossible in UTF-8) reaches the
    # database: UnicodeEncodeError on the llm_call write after the model was paid.
    payload = json.dumps(grade_body(answer="bắt tay \ud800 ba bước"))
    response = client_with(app, Scripted(GOOD), sessions).post(
        "/v1/grade", content=payload, headers=HEADERS
    )
    assert response.status_code in {200, 422}, (response.status_code, response.text[:200])


def test_t212_concurrent_requests_of_different_users_keep_their_own_rows(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # Red when: a run, nonce or row is shared between requests (a module-level buffer, one
    # session for all calls): rows land under the wrong user or a request fails.
    bodies = [grade_body() for _ in range(8)]
    client = client_with(app, Scripted(*[GOOD] * len(bodies)), sessions)

    def post(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        response = client.post("/v1/grade", json=body)
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(post, bodies))

    assert [status for status, _ in results] == [200] * len(bodies)
    assert len({data["run_id"] for _, data in results}) == len(bodies)
    for body, (_, data) in zip(bodies, results, strict=True):
        [run] = runs_of(engine, body["user_id"])
        [call] = calls_of(engine, body["user_id"])
        assert (str(run.id), str(call.id)) == (data["run_id"], data["llm_call_id"])
        assert call.pipeline_run_id == run.id
        assert run.status == "succeeded"
        assert call.user_id == uuid.UUID(body["user_id"])
        assert call.subject_id == uuid.UUID(body["subject_id"])


def test_b3_run_that_cannot_be_closed_is_503_not_a_grade(
    app: FastAPI, sessions: sessionmaker[Session], engine: Engine
) -> None:
    # Red when: a failure closing pipeline_run (third write: run, llm_call, close) is swallowed
    # and the grade is returned: the audit log would keep a run "running" for a graded answer.
    opened = {"n": 0}

    def third_commit_fails() -> Session:
        session = sessions()
        opened["n"] += 1
        if opened["n"] == 3:
            session.commit = _database_down  # type: ignore[method-assign]
        return session

    body = grade_body()
    llm = LlmClient(Scripted(GOOD), third_commit_fails, models={"grade": MODEL})
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_audit_sessions] = lambda: third_commit_fails
    client = TestClient(app, headers={SERVICE_TOKEN_HEADER: "test-service-token-0123456789abcdef"})
    response = client.post("/v1/grade", json=body)
    assert (response.status_code, response.json()) == (503, {"code": "audit_unavailable"})
    [run] = runs_of(engine, body["user_id"])
    assert run.status == "running"


def _database_down() -> None:
    raise OSError("database is down")
