"""POST /v1/generate-like (T9.6b, US-17): candidate practice questions in the style of a sample,
code-filtered and judged. Behind X-Service-Token; core-api is the caller, and only after the
learner pressed the button (AC1). Errors and status follow /v1/grade-practice: model trouble is a
200 with `status: "empty"` and a `failure`, or `status: "pending_ai"`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from ai_service.api.grade import (
    GradingDisabledError,
    get_audit_sessions,
    get_llm_client,
    limit_body,
)
from ai_service.db.session import SessionFactory
from ai_service.llm.client import LlmClient
from ai_service.logging import set_user_id
from ai_service.tasks.generate_like import LikeInputError
from ai_service.tasks.like_run import GenerateLikeBody, GenerateLikeResponse, run_generate_like

router = APIRouter(prefix="/v1", dependencies=[Depends(limit_body)])


@router.post("/generate-like")
def generate_like(
    body: GenerateLikeBody,
    llm: Annotated[LlmClient | None, Depends(get_llm_client)],
    sessions: Annotated[SessionFactory, Depends(get_audit_sessions)],
) -> GenerateLikeResponse:
    set_user_id(str(body.user_id))
    if llm is None:
        raise GradingDisabledError
    return run_generate_like(body, llm=llm, sessions=sessions)


async def _invalid(request: Request, exc: Exception) -> JSONResponse:
    # The rule name only (never request text): the request was too large or repeated a card.
    return JSONResponse({"code": "invalid_request"}, status_code=422)


def add_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(LikeInputError, _invalid)
