import io
import json
import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_service.logging import REQUEST_ID_HEADER, configure_logging, mask_email
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER

Lines = Callable[[], list[dict[str, Any]]]
SECRETS = {
    "answer_text": "TCP dùng bắt tay ba bước",
    "password": "hunter2-correct-horse",
    "token": "token-that-must-not-be-logged",
}


@pytest.fixture
def log_lines() -> Iterator[Lines]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, logging.getLogger("uvicorn.access").disabled)
    buffer = io.StringIO()
    configure_logging("ai-service", "DEBUG", stream=buffer)

    def lines() -> list[dict[str, Any]]:
        return [json.loads(line) for line in buffer.getvalue().splitlines()]

    yield lines
    root.handlers, root.level, logging.getLogger("uvicorn.access").disabled = saved


def raw(lines: Lines) -> str:
    return json.dumps(lines(), ensure_ascii=False)


def access_lines(lines: Lines) -> list[dict[str, Any]]:
    return [line for line in lines() if line["logger"] == "ai_service.access"]


def test_sensitive_fields_are_dropped_with_their_values(log_lines: Lines) -> None:
    logging.getLogger("ai_service.test").info("graded", extra={**SECRETS, "status": 200})
    [line] = log_lines()
    for name, value in SECRETS.items():
        assert name not in line
        assert value not in raw(log_lines)
    assert line["dropped_fields"] == sorted(SECRETS)
    assert line["service"] == "ai-service"


def test_email_field_is_always_masked(log_lines: Lines) -> None:
    logging.getLogger("ai_service.test").info("x", extra={"email": "nguyen@gmail.com"})
    assert log_lines()[0]["email"] == "n***@gmail.com"


def test_mask_email() -> None:
    assert mask_email("nguyen@gmail.com") == "n***@gmail.com"
    assert mask_email("not-an-email") == "***"


def test_exception_message_is_not_logged(log_lines: Lines) -> None:
    try:
        raise ValueError(SECRETS["password"])
    except ValueError:
        logging.getLogger("ai_service.test").exception("failed")
    assert log_lines()[0]["error_type"] == "ValueError"
    assert SECRETS["password"] not in raw(log_lines)


def test_uvicorn_access_log_is_disabled(log_lines: Lines) -> None:
    logging.getLogger("uvicorn.access").info('"GET /v1/ping?token=x HTTP/1.1" 200')
    assert log_lines() == []


def test_request_id_from_core_api_is_kept_and_logged(log_lines: Lines, service_token: str) -> None:
    response = TestClient(create_app()).get(
        "/v1/ping", headers={SERVICE_TOKEN_HEADER: service_token, REQUEST_ID_HEADER: "chain-42"}
    )
    assert response.headers[REQUEST_ID_HEADER] == "chain-42"
    [line] = access_lines(log_lines)
    assert (line["request_id"], line["path"], line["status"]) == ("chain-42", "/v1/ping", 200)


def test_rejected_request_is_logged_without_the_token(log_lines: Lines) -> None:
    response = TestClient(create_app()).get(
        "/v1/ping?token=leak", headers={SERVICE_TOKEN_HEADER: SECRETS["token"]}
    )
    assert response.status_code == 401
    [line] = access_lines(log_lines)
    assert line["status"] == 401
    assert line["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert SECRETS["token"] not in raw(log_lines)
    assert "leak" not in raw(log_lines)
