"""POST /v1/review-question (T7.9): the review question of one saved card. Behind
X-Service-Token; core-api is the caller. Errors are `{"code": ...}` like /v1/grade."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ai_service.api.grade import (
    GradingDisabledError,
    get_audit_sessions,
    get_llm_client,
    limit_body,
)
from ai_service.db.session import SessionFactory
from ai_service.llm.client import LlmClient
from ai_service.logging import set_user_id
from ai_service.tasks.review_question import (
    ReviewQuestionBody,
    ReviewQuestionResponse,
    run_review_question,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(limit_body)])


@router.post("/review-question")
def review_question(
    body: ReviewQuestionBody,
    llm: Annotated[LlmClient | None, Depends(get_llm_client)],
    sessions: Annotated[SessionFactory, Depends(get_audit_sessions)],
) -> ReviewQuestionResponse:
    set_user_id(str(body.user_id))
    if llm is None:
        raise GradingDisabledError
    return run_review_question(body, llm=llm, sessions=sessions)
