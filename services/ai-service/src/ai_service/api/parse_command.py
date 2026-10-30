"""POST /v1/parse-command (T9.1): one command line into one fixed operation.

Behind X-Service-Token; core-api is the caller (T9.2, cut at 8 s). Errors are `{"code": ...}` like
/v1/grade, which owns the shared handlers (413, 422 without echo, 502 llm_unavailable, 503
grading_disabled, 503 audit_unavailable, 429 quota_hard_cap: the command bar turns itself off on
it, AC8); this module adds one.

| Status | code | When |
|---|---|---|
| 502 | parse_command_invalid | the output broke the rules twice, or once with no time left |

Not understanding the line is not an error: 200 with `result.kind == "unclear"`.
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
from ai_service.commands.schema import ParseCommandRequest, ParseCommandResponse
from ai_service.db.session import SessionFactory
from ai_service.llm.client import LlmClient
from ai_service.logging import set_user_id
from ai_service.tasks.parse_command import ParseCommandInvalidError, parse_command

# A request with every limit reached (1050 titles of 120 non-ASCII characters, 60 000 characters
# in all, each up to 12 bytes escaped) stays under it; above it nothing is parsed.
MAX_BODY_BYTES = 1024 * 1024

_log = logging.getLogger(__name__)


async def limit_body(request: Request) -> None:
    if len(await request.body()) > MAX_BODY_BYTES:
        raise RequestTooLargeError


router = APIRouter(prefix="/v1", dependencies=[Depends(limit_body)])


@router.post("/parse-command")
def parse(
    body: ParseCommandRequest,
    llm: Annotated[LlmClient | None, Depends(get_llm_client)],
    sessions: Annotated[SessionFactory, Depends(get_audit_sessions)],
) -> ParseCommandResponse:
    set_user_id(str(body.user_id))
    if llm is None:
        raise GradingDisabledError
    return parse_command(body, llm=llm, sessions=sessions)


def add_error_handlers(app: FastAPI) -> None:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        _log.warning("parse_command failed", extra={"status": 502, "outcome": "invalid"})
        return JSONResponse({"code": "parse_command_invalid"}, status_code=502)

    app.add_exception_handler(ParseCommandInvalidError, handler)
