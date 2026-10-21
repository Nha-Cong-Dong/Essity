"""`GET /v1/me`: the signed-in account, without anything secret (ADR-0014)."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from core_api.api.deps import CurrentUser
from core_api.db.session import DbSession
from core_api.domain.baseline import needs_baseline
from core_api.repositories.baseline import BaselineRepository
from core_api.repositories.subject import SubjectRepository

router = APIRouter(prefix="/v1")


class Me(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool
    timezone: str
    day_start_hour: int
    # Where web sends the user after signing in: the baseline screen, then creating a subject,
    # then today (US-11 AC1, AC2; DESIGN §6.2).
    needs_baseline: bool
    has_subjects: bool


@router.get("/me")
def me(user: CurrentUser, session: DbSession) -> Me:
    verified = user.email_verified_at is not None
    has_baseline = BaselineRepository(session, user.id).get_mine() is not None
    return Me(
        id=user.id,
        email=user.email,
        email_verified=verified,
        timezone=user.timezone,
        day_start_hour=user.day_start_hour,
        needs_baseline=needs_baseline(
            verified=verified, has_baseline=has_baseline, skips=user.baseline_skips
        ),
        has_subjects=SubjectRepository(session, user.id).has_any(),
    )
