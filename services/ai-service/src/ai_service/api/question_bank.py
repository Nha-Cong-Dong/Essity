"""POST /v1/parse-question-bank (T8.1b, US-14): split a bank into questions, suggest their types
and link them to the syllabus sections core sent. Behind X-Service-Token; core-api is the caller,
and only for a document the learner marked as a question bank. Errors and status follow
/v1/grade-practice: model trouble is a 200 with `status: "partial"` or `"pending_ai"`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ai_service.api.grade import (
    GradingDisabledError,
    RequestTooLargeError,
    get_audit_sessions,
    get_llm_client,
)
from ai_service.db.session import SessionFactory
from ai_service.llm.client import LlmClient
from ai_service.logging import set_user_id
from ai_service.tasks.bank_run import ParseBankBody, ParseBankResponse, run_parse_question_bank

MAX_BODY_BYTES = 8 * 1024 * 1024  # a bank of a few hundred pages of text


async def limit_body(request: Request) -> None:
    if len(await request.body()) > MAX_BODY_BYTES:
        raise RequestTooLargeError


router = APIRouter(prefix="/v1", dependencies=[Depends(limit_body)])


@router.post("/parse-question-bank")
def parse_question_bank(
    body: ParseBankBody,
    llm: Annotated[LlmClient | None, Depends(get_llm_client)],
    sessions: Annotated[SessionFactory, Depends(get_audit_sessions)],
) -> ParseBankResponse:
    set_user_id(str(body.user_id))
    if llm is None:
        raise GradingDisabledError
    return run_parse_question_bank(body, llm=llm, sessions=sessions)
