"""POST /v1/grade-practice and /v1/draft-answer (T8.4, US-05 AC9-AC14): practice grading by rubric
and the AI-drafted reference answer. Behind X-Service-Token; core-api is the caller.

Errors are `{"code": ...}` like /v1/grade, which owns the shared handlers (413, 422 without echo,
503 grading_disabled, 503 audit_unavailable). Model trouble is not an error: 200 with
`status: "failed"` (the reply broke a rule) or `status: "pending_ai"` (quota or model down: core
keeps the answer and says it will be graded later).
"""

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
from ai_service.tasks.practice_run import (
    DraftAnswerBody,
    DraftAnswerResponse,
    GradePracticeBody,
    GradePracticeResponse,
    run_draft_answer,
    run_grade_practice,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(limit_body)])


@router.post("/grade-practice")
def grade_practice(
    body: GradePracticeBody,
    llm: Annotated[LlmClient | None, Depends(get_llm_client)],
    sessions: Annotated[SessionFactory, Depends(get_audit_sessions)],
) -> GradePracticeResponse:
    set_user_id(str(body.user_id))
    if llm is None:
        raise GradingDisabledError
    return run_grade_practice(body, llm=llm, sessions=sessions)


@router.post("/draft-answer")
def draft_answer(
    body: DraftAnswerBody,
    llm: Annotated[LlmClient | None, Depends(get_llm_client)],
    sessions: Annotated[SessionFactory, Depends(get_audit_sessions)],
) -> DraftAnswerResponse:
    set_user_id(str(body.user_id))
    if llm is None:
        raise GradingDisabledError
    return run_draft_answer(body, llm=llm, sessions=sessions)
