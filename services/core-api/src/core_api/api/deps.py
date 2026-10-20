"""Who is calling (ADR-0014): the session token in `Authorization: Bearer <token>`.

Web keeps the token in an httpOnly cookie and sends it in this header; it never travels in a
URL, so it stays out of access logs and traces (the span exporter blanks the header too).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from core_api.db.models import AuthSession, User
from core_api.db.session import DbSession
from core_api.logging import set_user_id
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.user import UserRepository

BEARER = "bearer"


@dataclass(frozen=True)
class SignedIn:
    user: User
    session: AuthSession


def _bearer_token(request: Request) -> str | None:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    token = token.strip()
    return token if scheme.lower() == BEARER and token else None


def signed_in(request: Request, session: DbSession) -> SignedIn:
    """The caller's live session and user; 401 otherwise. Slides the session's expiry."""
    now = datetime.now(UTC)
    token = _bearer_token(request)
    sessions = AuthSessionRepository(session)
    row = sessions.get_active(token, now) if token else None
    user = UserRepository(session).get(row.user_id) if row else None
    if row is None or user is None or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    sessions.touch(row, now)
    set_user_id(str(user.id))
    return SignedIn(user=user, session=row)


CurrentSession = Annotated[SignedIn, Depends(signed_in)]


def current_user(signed: CurrentSession) -> User:
    return signed.user


CurrentUser = Annotated[User, Depends(current_user)]


def verified_user(signed: CurrentSession) -> User:
    return signed.user


VerifiedUser = Annotated[User, Depends(verified_user)]
