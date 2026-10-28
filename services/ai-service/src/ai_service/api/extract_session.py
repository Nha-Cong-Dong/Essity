"""POST /v1/extract-session (T4.10): a learner's sentence into a proposed session record.

Behind X-Service-Token; core-api is the caller (T4.12, timeout 5 s). Errors are `{"code": ...}`
like /v1/grade, which owns the shared handlers (413, 422 without echo, 502 llm_unavailable,
503 grading_disabled, 503 audit_unavailable); this module adds one.

| Status | code | When |
|---|---|---|
| 502 | extract_invalid | the output broke the rules twice, or once with no time to ask again |
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from ai_service.api.grade import (
    GradingDisabledError,
    RequestTooLargeError,
    get_audit_sessions,
    get_llm_client,
)
from ai_service.db.session import SessionFactory
from ai_service.llm.client import LlmClient
from ai_service.logging import set_user_id
from ai_service.tasks.extract_models import ExtractRequest, ExtractResponse
from ai_service.tasks.extract_session import ExtractInvalidError, extract_session

# Real PDFs stay far below it (a few hundred entries of short titles: tens of KB). A request with
# every limit reached (6000 entries of 200 non-ASCII characters, escaped) fits; the extreme (6000
# titles of 500 characters) is refused with 413 on purpose, so memory stays bounded.
MAX_BODY_BYTES = 8 * 1024 * 1024

_log = logging.getLogger(__name__)


async def limit_body(request: Request) -> None:
    if len(await request.body()) > MAX_BODY_BYTES:
        raise RequestTooLargeError


router = APIRouter(prefix="/v1", dependencies=[Depends(limit_body)])


@router.post("/extract-session")
def extract(
    body: ExtractRequest,
    llm: Annotated[LlmClient | None, Depends(get_llm_client)],
    sessions: Annotated[SessionFactory, Depends(get_audit_sessions)],
) -> ExtractResponse:
    set_user_id(str(body.user_id))
    if llm is None:
        raise GradingDisabledError
    return extract_session(body, llm=llm, sessions=sessions)


def add_error_handlers(app: FastAPI) -> None:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        _log.warning("extract failed", extra={"status": 502, "outcome": "extract_invalid"})
        return JSONResponse({"code": "extract_invalid"}, status_code=502)

    app.add_exception_handler(ExtractInvalidError, handler)
