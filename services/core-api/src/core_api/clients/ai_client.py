import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

import httpx2
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from pydantic import ValidationError

from core_api.clients.grade_contract import GradeResponse
from core_api.config import Settings
from core_api.logging import REQUEST_ID_HEADER, request_id_var
from core_api.security.service_token import SERVICE_TOKEN_HEADER

__all__ = [
    "PING_TIMEOUT_SECONDS",
    "Graded",
    "NotGraded",
    "SERVICE_TOKEN_HEADER",
    "AiServiceClient",
    "AiServiceUnavailableError",
]

# Below web's 3 s timeout for core-api, so a hung ai-service is reported as such by /v1/ping.
PING_TIMEOUT_SECONDS = 2.0
# The AI leg of one grading (plan D-5, 🟡7): 10 s a call, 20 s in all, no retry with < 3 s left.
GRADE_CALL_SECONDS = 10.0
GRADE_TOTAL_SECONDS = 20.0
GRADE_MIN_RETRY_SECONDS = 3.0

Failure = Literal["unavailable", "invalid", "disabled"]
_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Graded:
    response: GradeResponse


@dataclass(frozen=True)
class NotGraded:
    """Grading failed; the answer stays saved and "Chấm lại" is offered (PLAN T2.13).
    `reason` is a stable code for the log, never ai-service's body (ADR-0013)."""

    failure: Failure
    reason: str


# ai-service's error codes (T2.12, PLAN T2.13 retry table, plan 🟠2): (failure, retry?).
_CODES: dict[str, tuple[Failure, bool]] = {
    "llm_unavailable": ("unavailable", True),
    "grade_invalid": ("invalid", False),
    "request_too_large": ("invalid", False),
    "invalid_request": ("invalid", False),
    "grading_disabled": ("disabled", False),
    "audit_unavailable": ("unavailable", False),
}


class AiServiceUnavailableError(Exception):
    """ai-service did not answer, timed out, or answered with an error status."""


class AiServiceClient:
    """Synchronous client for ai-service (ADR-0005: core-api routes are sync)."""

    def __init__(self, http: httpx2.Client) -> None:
        self._http = http

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx2.BaseTransport | None = None
    ) -> "AiServiceClient":
        http = httpx2.Client(
            base_url=settings.ai_service_url,
            headers={SERVICE_TOKEN_HEADER: settings.ai_service_token.get_secret_value()},
            timeout=settings.ai_service_timeout_seconds,
            transport=transport,
            event_hooks={"request": [_forward_request_id]},
        )
        # Client span + W3C traceparent header, so ai-service continues the same trace.
        # Its signature names the original httpx package, which is not installed here.
        HTTPX2ClientInstrumentor.instrument_client(http)  # pyright: ignore[reportUnknownMemberType]
        return cls(http)

    def ping(self) -> None:
        try:
            response = self._http.get("/v1/ping", timeout=PING_TIMEOUT_SECONDS)
            response.raise_for_status()
        except httpx2.HTTPError as exc:
            raise AiServiceUnavailableError(str(exc)) from exc

    def grade(
        self, payload: Mapping[str, object], *, clock: Callable[[], float] = time.monotonic
    ) -> Graded | NotGraded:
        """POST /v1/grade, retried once when the failure may clear (plan 🟠2). Never raises
        for ai-service's answers; never logs a body, which may echo the answer (ADR-0013)."""
        started = clock()
        outcome, retry = self._grade_once(payload, GRADE_CALL_SECONDS)
        if not retry:
            return outcome
        left = GRADE_TOTAL_SECONDS - (clock() - started)
        if left < GRADE_MIN_RETRY_SECONDS:
            return outcome
        return self._grade_once(payload, min(GRADE_CALL_SECONDS, left))[0]

    def _grade_once(
        self, payload: Mapping[str, object], timeout: float
    ) -> tuple[Graded | NotGraded, bool]:
        try:
            response = self._http.post("/v1/grade", json=dict(payload), timeout=timeout)
        except httpx2.TimeoutException:
            return _failed("unavailable", "timeout", None), True
        except httpx2.TransportError:
            return _failed("unavailable", "connection_error", None), True
        status = response.status_code
        if 200 <= status < 300:
            try:
                return Graded(GradeResponse.model_validate_json(response.content)), False
            except (ValidationError, ValueError):
                # The parse error carries the input (`missing` is text drawn from the answer).
                return _failed("invalid", "response_schema", status), False
        code = _error_code(response)
        if code in _CODES:
            failure, retry = _CODES[code]
            return _failed(failure, code, status), retry
        if status in (413, 422):
            return _failed("invalid", "refused", status), False
        if status >= 500:
            return _failed("unavailable", "server_error", status), True
        return _failed("unavailable", "client_error", status), False

    def close(self) -> None:
        self._http.close()


def _forward_request_id(request: httpx2.Request) -> None:
    # Same id on both sides, so one user request can be followed across services.
    request_id = request_id_var.get()
    if request_id is not None:
        request.headers[REQUEST_ID_HEADER] = request_id


def _error_code(response: httpx2.Response) -> str | None:
    try:
        body: object = json.loads(response.content)
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    code = cast(dict[str, object], body).get("code")
    return code if isinstance(code, str) else None


def _failed(failure: Failure, reason: str, status: int | None) -> NotGraded:
    _log.warning("grade call failed", extra={"outcome": reason, "upstream_status": status})
    return NotGraded(failure, reason)
