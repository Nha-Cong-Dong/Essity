"""JSON logs on stdout, one object per line (ADR-0013).

Personal data stays out of the logs by construction, not by care at each call site:

- Fields passed with `extra=` are written only if they are in `ALLOWED_FIELDS`. Anything else
  (`answer_text`, `password`, `token`, ...) is dropped, value and all; only its name is kept in
  `dropped_fields` so the mistake is visible.
- `email` is always masked (`n***@gmail.com`).
- Exceptions are logged as type and stack, without the message: messages often embed input
  values (pydantic's ValidationError prints `input_value=...`).
- The message itself is free text, so keep it constant and put data in allowed fields.
- Libraries that format data into their messages are in `_DATA_IN_MESSAGE_LOGGERS`: their
  lines keep only the constant event name they pass as `action`, and none of their extras.
  Procrastinate, for one, writes every job's arguments (email addresses) into its messages;
  the Anthropic SDK writes whole requests and responses (a learner's answer) at DEBUG.
- uvicorn's access log is replaced by `log_requests`, which logs the path without the query
  string (email verification links will carry tokens there, ADR-0014). httpx2's own
  "HTTP Request: GET <url>" lines are silenced for the same reason.

`request_id` and `user_id` come from context variables, so every line inside a request carries
them without being passed around. Inside a traced request, `trace_id` and `span_id` link the line
to its trace in Jaeger.
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
from opentelemetry import trace

REQUEST_ID_HEADER = "X-Request-ID"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)


class _RequestUser:
    """The signed-in user of one request, shared by every context copy the request makes.

    FastAPI runs each sync dependency and the endpoint in their own copy of the context, so a
    `user_id_var.set` in the auth dependency is gone by the time the endpoint logs, and the
    access line is written outside both. The middleware puts one of these in the context first;
    every copy then holds the same object, and `set_user_id` fills it in.
    """

    user_id: str | None = None


_request_user_var: ContextVar[_RequestUser | None] = ContextVar("request_user", default=None)


def set_user_id(user_id: str) -> None:
    """Name the user for every log line of the current request (or job) from here on."""
    user_id_var.set(user_id)
    request_user = _request_user_var.get()
    if request_user is not None:
        request_user.user_id = user_id


def current_user_id() -> str | None:
    request_user = _request_user_var.get()
    return user_id_var.get() or (request_user.user_id if request_user else None)


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
        "job_kind",
        "job_id",
        "attempt",
        "outcome",
        "deleted_count",  # purge_unverified
        "jobs_failed_recent",  # job_health (R05)
        "jobs_failed_total",
        "jobs_stalled",
        "event",  # security events (security/audit.py)
        "ip_hash",  # keyed hash, never the IP itself
        "llm_call_id",  # ai-service: the audit row holding the call itself (ADR-0013)
        "provider",  # anthropic | fake
        # Events (T4.2 outbox relay, T4.4 consumer): ids, counts and class names, never a payload.
        "event_id",
        "event_type",
        "event_count",
        "error_type",  # exception class name only
        "deliveries",
        "reason",  # dead letter: exception class name or a code (contracts/events/README.md)
        "outbox_unsent_stale",  # job_health (plan Y8)
    }
)
# Top-level logger names; see the module docstring.
_DATA_IN_MESSAGE_LOGGERS = frozenset({"procrastinate", "anthropic"})

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
        data_in_message = record.name.partition(".")[0] in _DATA_IN_MESSAGE_LOGGERS
        message = str(record.__dict__.get("action") or "-") if data_in_message else None
        line: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "logger": record.name,
            "message": record.getMessage() if message is None else message,
            "request_id": request_id_var.get(),
            "user_id": current_user_id(),
        }
        span = trace.get_current_span().get_span_context()
        if span.is_valid:
            line["trace_id"] = format(span.trace_id, "032x")
            line["span_id"] = format(span.span_id, "016x")
        dropped: list[str] = []
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key in _IGNORED_EXTRAS or data_in_message:
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
    # httpx2 logs every outgoing URL, query string included, at INFO; the Anthropic SDK logs
    # request and response bodies at DEBUG. httpx/httpcore in case a library brings them.
    for name in ("httpx2", "httpcore2", "httpx", "httpcore", "anthropic"):
        logging.getLogger(name).setLevel(logging.WARNING)


async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request id (reusing a well-formed incoming one) and log one line per request."""
    incoming = request.headers.get(REQUEST_ID_HEADER)
    request_id = incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
    token = request_id_var.set(request_id)
    user_token = _request_user_var.set(_RequestUser())
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
        _request_user_var.reset(user_token)
        request_id_var.reset(token)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
