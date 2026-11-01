import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

import httpx2
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from pydantic import ValidationError

from core_api.clients.extract_contract import Clarify, ExtractAnswer, NoteOnly, Proposed
from core_api.clients.grade_contract import GradeResponse
from core_api.clients.practice_contract import DraftAnswerReply, PracticeGradeReply
from core_api.clients.review_question_contract import ReviewQuestionReply
from core_api.config import Settings
from core_api.logging import REQUEST_ID_HEADER, request_id_var
from core_api.security.service_token import SERVICE_TOKEN_HEADER

__all__ = [
    "PING_TIMEOUT_SECONDS",
    "Extracted",
    "Graded",
    "NotExtracted",
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
GRADE_CONNECT_SECONDS = 2.0

# The /v1/extract-session leg (T4.12): one try, connecting capped at 1 s, no retry.
EXTRACT_CONNECT_SECONDS = 1.0

Failure = Literal["unavailable", "invalid", "disabled", "quota"]
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
    # The account is at its hard cost cap (T2.11): a retry or a queued job would only be refused
    # again, so it ends here and the answer stays saved (T2.11b).
    "quota_hard_cap": ("quota", False),
}


@dataclass(frozen=True)
class Extracted:
    response: Proposed | NoteOnly | Clarify


@dataclass(frozen=True)
class NotExtracted:
    """Extraction failed; the learner gets the manual form (US-02 AC4). `reason` is a stable
    code for the log, never ai-service's body, which may echo the description (ADR-0013)."""

    failure: Failure
    reason: str


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
            # One budget per phase, connecting capped at 2 s (review 🟡3): a host that does not
            # answer leaves time for the retry.
            response = self._http.post(
                "/v1/grade",
                json=dict(payload),
                timeout=httpx2.Timeout(timeout, connect=min(GRADE_CONNECT_SECONDS, timeout)),
            )
        except httpx2.TimeoutException:
            return _failed("unavailable", "timeout", None, retry=True), True
        except httpx2.RequestError:  # transport, decoding, redirects: may clear (review 🟡5)
            return _failed("unavailable", "connection_error", None, retry=True), True
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
            return _failed(failure, code, status, retry=retry), retry
        if status in (413, 422):
            return _failed("invalid", "refused", status), False
        if status >= 500:
            return _failed("unavailable", "server_error", status, retry=True), True
        return _failed("unavailable", "client_error", status), False

    def extract_session(
        self, payload: Mapping[str, object], *, timeout: float
    ) -> Extracted | NotExtracted:
        """POST /v1/extract-session within `timeout` seconds, once. Never raises for ai-service's
        answers; never logs a body (ADR-0013)."""
        try:
            response = self._http.post(
                "/v1/extract-session",
                json=dict(payload),
                timeout=httpx2.Timeout(timeout, connect=min(EXTRACT_CONNECT_SECONDS, timeout)),
            )
        except httpx2.TimeoutException:
            return _extract_failed("unavailable", "timeout", None)
        except httpx2.RequestError:
            return _extract_failed("unavailable", "connection_error", None)
        status = response.status_code
        if 200 <= status < 300:
            try:
                answer = ExtractAnswer.model_validate({"answer": json.loads(response.content)})
            except (ValidationError, ValueError):
                return _extract_failed("invalid", "response_schema", status)
            return Extracted(answer.answer)
        code = _error_code(response)
        if code in _CODES:
            return _extract_failed(_CODES[code][0], code, status)
        if status in (413, 422):
            return _extract_failed("invalid", "refused", status)
        return _extract_failed(
            "unavailable", "server_error" if status >= 500 else "client_error", status
        )

    def grade_practice(self, payload: Mapping[str, object]) -> PracticeGradeReply | NotGraded:
        """POST /v1/grade-practice, once (T8.4). Never raises for ai-service's answers; never
        logs a body, which may echo the answer (ADR-0013)."""
        return self._practice("/v1/grade-practice", payload, PracticeGradeReply)

    def draft_answer(self, payload: Mapping[str, object]) -> DraftAnswerReply | NotGraded:
        """POST /v1/draft-answer, once (T8.4)."""
        return self._practice("/v1/draft-answer", payload, DraftAnswerReply)

    def review_question(self, payload: Mapping[str, object]) -> ReviewQuestionReply | NotGraded:
        """POST /v1/review-question, once (T7.9): the review question of one saved card."""
        return self._practice("/v1/review-question", payload, ReviewQuestionReply)

    def _practice[R: (PracticeGradeReply, DraftAnswerReply, ReviewQuestionReply)](
        self, path: str, payload: Mapping[str, object], reply: type[R]
    ) -> R | NotGraded:
        try:
            response = self._http.post(
                path,
                json=dict(payload),
                timeout=httpx2.Timeout(
                    GRADE_CALL_SECONDS, connect=min(GRADE_CONNECT_SECONDS, GRADE_CALL_SECONDS)
                ),
            )
        except httpx2.TimeoutException:
            return _failed("unavailable", "timeout", None)
        except httpx2.RequestError:
            return _failed("unavailable", "connection_error", None)
        status = response.status_code
        if 200 <= status < 300:
            try:
                return reply.model_validate_json(response.content)
            except (ValidationError, ValueError):
                return _failed("invalid", "response_schema", status)
        code = _error_code(response)
        if code in _CODES:
            return _failed(_CODES[code][0], code, status)
        if status in (413, 422):
            return _failed("invalid", "refused", status)
        return _failed("unavailable", "server_error" if status >= 500 else "client_error", status)

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


def _failed(failure: Failure, reason: str, status: int | None, *, retry: bool = False) -> NotGraded:
    # What a retry cannot clear is a fault to look at (plan "Bảng retry", review 🟡4); grading
    # switched off on purpose is not.
    level = logging.WARNING if retry or failure in ("disabled", "quota") else logging.ERROR
    _log.log(level, "grade call failed", extra={"outcome": reason, "upstream_status": status})
    return NotGraded(failure, reason)


def _extract_failed(failure: Failure, reason: str, status: int | None) -> NotExtracted:
    level = logging.WARNING if failure != "invalid" else logging.ERROR
    _log.log(level, "extract call failed", extra={"outcome": reason, "upstream_status": status})
    return NotExtracted(failure, reason)
