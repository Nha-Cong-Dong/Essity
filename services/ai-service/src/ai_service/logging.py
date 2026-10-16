"""JSON logs on stdout, one object per line (ADR-0013).

Personal data stays out of the logs by construction, not by care at each call site:

- Fields passed with `extra=` are written only if they are in `ALLOWED_FIELDS`. Anything else
  (`answer_text`, `password`, `token`, ...) is dropped, value and all; only its name is kept in
  `dropped_fields` so the mistake is visible.
- `email` is always masked (`n***@gmail.com`).
- Exceptions are logged as type and stack, without the message: messages often embed input
  values (pydantic's ValidationError prints `input_value=...`).
- The message itself is free text, so keep it constant and put data in allowed fields.
- uvicorn's access log is replaced by `log_requests`, which logs the path without the query
  string (email verification links will carry tokens there, ADR-0014). httpx2's own
  "HTTP Request: GET <url>" lines are silenced for the same reason.

`request_id` and `user_id` come from context variables, so every line inside a request carries
them without being passed around.
"""

import json
import logging
import re
import sys
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

from fastapi import Request, Response

REQUEST_ID_HEADER = "X-Request-ID"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

# Fields a call site may add with `extra=`. Add to this list deliberately, never a free-text
# field written by the user.
ALLOWED_FIELDS = frozenset(
    {
        "method",
        "path",
        "status",
        "duration_ms",
        "email",  # masked by the formatter
        "upstream",
        "upstream_status",
    }
)

_STANDARD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
# Not personal data, just noise: uvicorn repeats the message with ANSI colors.
_IGNORED_EXTRAS = frozenset({"color_message"})
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_QUIET_PATHS = frozenset({"/healthz"})  # polled every few seconds by Docker

_log = logging.getLogger("ai_service.access")


def mask_email(email: str) -> str:
    """`nguyen@gmail.com` -> `n***@gmail.com`. Anything that is not an email -> `***`."""
    local, at, domain = email.strip().rpartition("@")
    if not at or not local or not domain:
        return "***"
    return f"{local[0]}***@{domain}"


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
        }
        dropped: list[str] = []
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key in _IGNORED_EXTRAS:
                continue
            if key in ALLOWED_FIELDS:
                line[key] = mask_email(str(value)) if key == "email" else value
            else:
                dropped.append(key)
        if dropped:
            line["dropped_fields"] = sorted(dropped)
        if record.exc_info and record.exc_info[0] is not None:
            exc_type, _, tb = record.exc_info
            line["error_type"] = exc_type.__name__
            line["stack"] = "".join(traceback.format_tb(tb))
        return json.dumps(line, ensure_ascii=False, default=str)


def configure_logging(service: str, level: str, stream: TextIO | None = None) -> None:
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn installs its own handlers; route its server logs through ours instead.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    # Replaced by log_requests: it would log query strings.
    logging.getLogger("uvicorn.access").disabled = True
    # httpx2 logs every outgoing URL, query string included, at INFO.
    for name in ("httpx2", "httpcore2"):
        logging.getLogger(name).setLevel(logging.WARNING)


async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request id (reusing a well-formed incoming one) and log one line per request."""
    incoming = request.headers.get(REQUEST_ID_HEADER)
    request_id = incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    fields: dict[str, Any] = {"method": request.method, "path": request.url.path}
    try:
        try:
            response = await call_next(request)
        except Exception:
            fields["duration_ms"] = _elapsed_ms(started)
            _log.exception("request failed", extra={**fields, "status": 500})
            raise
        fields["duration_ms"] = _elapsed_ms(started)
        level = logging.DEBUG if request.url.path in _QUIET_PATHS else logging.INFO
        _log.log(level, "request", extra={**fields, "status": response.status_code})
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        request_id_var.reset(token)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
