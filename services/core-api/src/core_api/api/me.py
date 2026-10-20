"""`GET /v1/me`: the signed-in account, without anything secret (ADR-0014)."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from core_api.api.deps import CurrentUser

router = APIRouter(prefix="/v1")


class Me(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool
    timezone: str
    day_start_hour: int


@router.get("/me")
def me(user: CurrentUser) -> Me:
    return Me(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified_at is not None,
        timezone=user.timezone,
        day_start_hour=user.day_start_hour,
    )
