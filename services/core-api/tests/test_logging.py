import io
import json
import logging
from collections.abc import Callable, Iterator
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import AiServiceClient
from core_api.config import get_settings
from core_api.logging import (
    REQUEST_ID_HEADER,
    configure_logging,
    log_requests,
    mask_email,
    request_id_var,
)
from core_api.main import app

Lines = Callable[[], list[dict[str, Any]]]
SECRETS = {
    "answer_text": "TCP dùng bắt tay ba bước",
    "password": "hunter2-correct-horse",
    "token": "token-that-must-not-be-logged",
}


@pytest.fixture
def log_lines() -> Iterator[Lines]:
    """Route all logging to a buffer, as configure_logging does in production."""
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, logging.getLogger("uvicorn.access").disabled)
    buffer = io.StringIO()
    configure_logging("core-api", "DEBUG", stream=buffer)

    def lines() -> list[dict[str, Any]]:
        return [json.loads(line) for line in buffer.getvalue().splitlines()]

    yield lines
    root.handlers, root.level, logging.getLogger("uvicorn.access").disabled = saved


@pytest.fixture
def raw_output(log_lines: Lines) -> Callable[[], str]:
    return lambda: json.dumps(log_lines(), ensure_ascii=False)


# --- Allowed fields: the "done when" of T0.9 -------------------------------------------------


def test_sensitive_fields_are_dropped_with_their_values(
    log_lines: Lines, raw_output: Callable[[], str]
) -> None:
    logging.getLogger("core_api.test").info("graded", extra={**SECRETS, "status": 200})
    [line] = log_lines()
    for name, value in SECRETS.items():
        assert name not in line
        assert value not in raw_output()
    assert line["dropped_fields"] == sorted(SECRETS)
    assert line["status"] == 200


def test_messaging_fields_are_logged(log_lines: Lines) -> None:
    # Red when: the relay, the consumer or job_health log a count or an id that is dropped, so
    # an outage of the event pipeline leaves no trace (T4.2, T4.4, plan Y8).
    fields = {
        "event_id": "6e5d4c3b-2a19-4807-a6b5-c4d3e2f1a000",
        "event_type": "session.confirmed.v1",
        "event_count": 3,
        "error_type": "ConnectionError",
        "deliveries": 5,
        "reason": "invalid_envelope",
        "outbox_unsent_stale": 2,
    }
    logging.getLogger("core_api.messaging").info("relayed", extra=fields)
    [line] = log_lines()
    assert {name: line.get(name) for name in fields} == fields
    assert "dropped_fields" not in line


def test_every_line_has_the_base_fields(log_lines: Lines) -> None:
    logging.getLogger("core_api.test").warning("something")
    [line] = log_lines()
    assert line["service"] == "core-api"
    assert line["level"] == "WARNING"
    assert line["message"] == "something"
    assert {"timestamp", "logger", "request_id", "user_id"} <= line.keys()


def test_email_field_is_always_masked(log_lines: Lines, raw_output: Callable[[], str]) -> None:
    logging.getLogger("core_api.test").info("signup", extra={"email": "nguyen@gmail.com"})
    assert log_lines()[0]["email"] == "n***@gmail.com"
    assert "nguyen@" not in raw_output()


@pytest.mark.parametrize(
    ("email", "masked"),
    [
        ("nguyen@gmail.com", "n***@gmail.com"),
        ("  A.B@uni.edu.vn ", "A***@uni.edu.vn"),
        ("a@b.c", "a***@b.c"),
        ("not-an-email", "***"),
        ("@gmail.com", "***"),
        ("nguyen@", "***"),
        ("", "***"),
    ],
)
def test_mask_email(email: str, masked: str) -> None:
    assert mask_email(email) == masked


def test_exception_message_is_not_logged(log_lines: Lines, raw_output: Callable[[], str]) -> None:
    try:
        raise ValueError(f"input_value={SECRETS['password']}")
    except ValueError:
        logging.getLogger("core_api.test").exception("failed")
    [line] = log_lines()
    assert line["error_type"] == "ValueError"
    assert "test_exception_message_is_not_logged" in line["stack"]
    assert SECRETS["password"] not in raw_output()


def test_library_messages_with_data_keep_only_the_event_name(
    log_lines: Lines, raw_output: Callable[[], str]
) -> None:
    logging.getLogger("procrastinate.worker.w-0").info(
        f"Starting job send_email[7](payload={{'token': '{SECRETS['token']}'}})",
        extra={"action": "start_job", "job": {"task_kwargs": SECRETS}},
    )
    [line] = log_lines()
    assert line["message"] == "start_job"
    assert "dropped_fields" not in line
    assert SECRETS["token"] not in raw_output()


def test_uvicorn_access_log_is_disabled(log_lines: Lines) -> None:
    logging.getLogger("uvicorn.access").info('127.0.0.1 - "GET /verify?token=x HTTP/1.1" 200')
    assert log_lines() == []


# --- Request middleware ----------------------------------------------------------------------


def test_request_gets_an_id_and_one_access_line(log_lines: Lines) -> None:
    response = TestClient(app).get("/healthz")
    request_id = response.headers[REQUEST_ID_HEADER]
    [line] = [line for line in log_lines() if line["logger"] == "core_api.access"]
    assert line["request_id"] == request_id
    assert line["method"] == "GET"
    assert line["path"] == "/healthz"
    assert line["status"] == 200
    assert line["duration_ms"] >= 0


def test_well_formed_incoming_request_id_is_kept() -> None:
    response = TestClient(app).get("/healthz", headers={REQUEST_ID_HEADER: "abc-123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc-123"


@pytest.mark.parametrize("bad", ["x" * 65, "has space", 'quote"', "semi;colon", "<script>"])
def test_malformed_incoming_request_id_is_replaced(bad: str) -> None:
    response = TestClient(app).get("/healthz", headers={REQUEST_ID_HEADER: bad})
    assert response.headers[REQUEST_ID_HEADER] != bad
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_access_line_has_no_query_string(log_lines: Lines, raw_output: Callable[[], str]) -> None:
    TestClient(app).get(f"/healthz?token={SECRETS['token']}")
    assert SECRETS["token"] not in raw_output()


def test_outgoing_http_urls_are_not_logged(log_lines: Lines, raw_output: Callable[[], str]) -> None:
    transport = httpx2.MockTransport(lambda request: httpx2.Response(200))
    with httpx2.Client(transport=transport) as client:
        client.get(f"https://oauth.example/token?code={SECRETS['token']}")
    assert SECRETS["token"] not in raw_output()


def test_request_id_does_not_leak_outside_the_request() -> None:
    TestClient(app).get("/healthz")
    assert request_id_var.get() is None


def test_core_api_forwards_request_id_to_ai_service() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"status": "ok"})

    ai_client = AiServiceClient.from_settings(get_settings(), httpx2.MockTransport(handler))
    app.dependency_overrides[get_ai_client] = lambda: ai_client
    try:
        response = TestClient(app).get("/v1/ping", headers={REQUEST_ID_HEADER: "chain-42"})
    finally:
        app.dependency_overrides.clear()
        ai_client.close()
    assert response.status_code == 200
    assert seen[0].headers[REQUEST_ID_HEADER] == "chain-42"


def test_failed_request_is_logged_with_type_and_without_message(
    log_lines: Lines, raw_output: Callable[[], str]
) -> None:
    failing = FastAPI()
    failing.middleware("http")(log_requests)

    @failing.get("/boom")
    def boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError(SECRETS["answer_text"])

    response = TestClient(failing, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    [line] = [line for line in log_lines() if line["logger"] == "core_api.access"]
    assert line["level"] == "ERROR"
    assert line["status"] == 500
    assert line["error_type"] == "RuntimeError"
    assert line["request_id"] is not None
    assert SECRETS["answer_text"] not in raw_output()
