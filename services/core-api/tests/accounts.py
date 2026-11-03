"""A signed-in account for HTTP tests of business endpoints: the user and its auth headers."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from core_api.db.models import User
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.user import UserRepository


def fresh_username() -> str:
    """A legal, unused username (D2): a letter, then 12 hex characters."""
    return f"u{uuid.uuid4().hex[:12]}"


def signed_in(session: Session, *, verified: bool = True) -> tuple[User, dict[str, str]]:
    user = UserRepository(session).create(f"user-{uuid.uuid4().hex[:12]}@example.com")
    session.flush()
    if verified:
        user.email_verified_at = datetime.now(UTC)
    token, _ = AuthSessionRepository(session).create(user.id, datetime.now(UTC))
    session.flush()
    return user, {"Authorization": f"Bearer {token}"}


def user_insert(connection: Connection | Session, id_param: str, email_param: str) -> TextClause:
    """Raw INSERT of a user for migration tests that seed at whatever revision the database is at:
    from 0035 on `username` is required, before it the column does not exist."""
    has_username = connection.execute(
        text(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()"
            " AND table_name = 'user' AND column_name = 'username'"
        )
    ).first()
    if not has_username:
        return text(f'INSERT INTO "user" (id, email) VALUES (:{id_param}, :{email_param})')
    return text(
        f'INSERT INTO "user" (id, email, username) VALUES (:{id_param}, :{email_param},'
        f" chr(117) || substr(md5(CAST(:{id_param} AS text)), 1, 12))"
    )
