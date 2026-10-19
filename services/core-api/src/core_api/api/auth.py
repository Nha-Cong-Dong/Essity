"""Account endpoints (ADR-0014). Sign-up, login and the rest arrive with T1.7–T1.10."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core_api.db.session import DbSession
from core_api.domain.auth.tokens import TokenPurpose
from core_api.repositories.email_token import EmailTokenRepository
from core_api.repositories.user import UserRepository

router = APIRouter(prefix="/v1/auth")


class TokenBody(BaseModel):
    # In the body, never the URL: request paths are logged and traced, bodies are not.
    token: str = Field(min_length=1, max_length=100)


@router.post("/verify-email")
def verify_email(body: TokenBody, session: DbSession) -> dict[str, str]:
    now = datetime.now(UTC)
    user_id = EmailTokenRepository(session).consume(body.token, TokenPurpose.VERIFY_EMAIL, now)
    user = UserRepository(session).get(user_id) if user_id else None
    if user is None or user.deleted_at is not None:
        # Unknown, used, expired and deleted-account links get the same answer (US-12 AC2).
        raise HTTPException(status_code=400, detail="invalid_or_expired_token")
    if user.email_verified_at is None:
        user.email_verified_at = now
    return {"status": "verified"}
