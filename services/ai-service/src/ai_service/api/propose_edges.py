"""POST /v1/propose-edges (T9.9): relations of one saved card to some others. Behind
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
from ai_service.tasks.propose_edges import (
    ProposeEdgesBody,
    ProposeEdgesResponse,
    run_propose_edges,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(limit_body)])


@router.post("/propose-edges")
def propose_edges(
    body: ProposeEdgesBody,
    llm: Annotated[LlmClient | None, Depends(get_llm_client)],
    sessions: Annotated[SessionFactory, Depends(get_audit_sessions)],
) -> ProposeEdgesResponse:
    set_user_id(str(body.user_id))
    if llm is None:
        raise GradingDisabledError
    return run_propose_edges(body, llm=llm, sessions=sessions)
