"""POST /v1/grade (T2.12): grade one answer. Behind X-Service-Token; core-api is the caller.

Errors are `{"code": ...}` with a stable code, never the model's raw output (🟠9). What core
should retry (T2.13): `llm_unavailable` and connection errors only.

| Status | code | When |
|---|---|---|
| 422 | invalid_request | the body breaks the contract (no input echoed back) |
| 413 | request_too_large | body over `MAX_BODY_BYTES` |
| 502 | grade_invalid | the output broke R03 twice |
| 502 | llm_unavailable | provider error, timeout, or the 9 s deadline |
| 503 | grading_disabled | AI_LLM_PROVIDER=disabled; nothing is written |
| 503 | audit_unavailable | pipeline_run or llm_call could not be written |
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ai_service.db.session import SessionFactory, get_session_factory
from ai_service.llm.client import AuditUnavailableError, LlmClient, LlmUnavailableError
from ai_service.logging import set_user_id
from ai_service.tasks.grade import GradeInvalidError, grade_answer
from ai_service.tasks.grade_models import GradeRequest, GradeResponse

# Above the largest valid request in any JSON encoding: about 29 000 characters of text, up to
# 6 bytes each when escaped as \uXXXX. Below it nothing valid is refused; above it, nothing is
# parsed further.
MAX_BODY_BYTES = 256 * 1024

_log = logging.getLogger(__name__)


class GradingDisabledError(Exception):
    """AI_LLM_PROVIDER=disabled."""


class RequestTooLargeError(Exception):
    pass


def get_llm_client(request: Request) -> LlmClient | None:
    """Built at startup (main.lifespan); None when grading is disabled."""
    client: LlmClient | None = request.app.state.llm_client
    return client


def get_audit_sessions() -> SessionFactory:
    return get_session_factory()


async def limit_body(request: Request) -> None:
    # Async on purpose: reading the body is awaited, no blocking I/O here.
    if len(await request.body()) > MAX_BODY_BYTES:
        raise RequestTooLargeError


router = APIRouter(prefix="/v1", dependencies=[Depends(limit_body)])


@router.post("/grade")
def grade(
    body: GradeRequest,
    llm: Annotated[LlmClient | None, Depends(get_llm_client)],
    sessions: Annotated[SessionFactory, Depends(get_audit_sessions)],
) -> GradeResponse:
    set_user_id(str(body.user_id))
    if llm is None:
        raise GradingDisabledError
    return grade_answer(body, llm=llm, sessions=sessions)


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse({"code": code}, status_code=status)


async def _invalid_request(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # loc, type and msg only: pydantic's `input` (and `ctx`) would echo the answer back.
    errors = [
        {"loc": list(error.get("loc", ())), "type": error.get("type"), "msg": error.get("msg")}
        for error in exc.errors()
    ]
    return JSONResponse({"code": "invalid_request", "errors": errors}, status_code=422)


def add_error_handlers(app: FastAPI) -> None:
    codes: list[tuple[type[Exception], int, str]] = [
        (RequestTooLargeError, 413, "request_too_large"),
        (GradeInvalidError, 502, "grade_invalid"),
        (LlmUnavailableError, 502, "llm_unavailable"),
        (GradingDisabledError, 503, "grading_disabled"),
        (AuditUnavailableError, 503, "audit_unavailable"),
    ]
    for exception, status, code in codes:

        async def handler(
            request: Request, exc: Exception, status: int = status, code: str = code
        ) -> JSONResponse:
            _log.warning("grade failed", extra={"status": status, "outcome": code})
            return _error(status, code)

        app.add_exception_handler(exception, handler)
    app.add_exception_handler(RequestValidationError, _invalid_request)
