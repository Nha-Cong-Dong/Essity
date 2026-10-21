"""A signed-in account for HTTP tests of business endpoints: the user and its auth headers."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from core_api.db.models import User
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.user import UserRepository


def signed_in(session: Session, *, verified: bool = True) -> tuple[User, dict[str, str]]:
    user = UserRepository(session).create(f"user-{uuid.uuid4().hex[:12]}@example.com")
    session.flush()
    if verified:
        user.email_verified_at = datetime.now(UTC)
    token, _ = AuthSessionRepository(session).create(user.id, datetime.now(UTC))
    session.flush()
    return user, {"Authorization": f"Bearer {token}"}
