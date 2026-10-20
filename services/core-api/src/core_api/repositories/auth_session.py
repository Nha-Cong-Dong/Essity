"""Signed-in sessions (ADR-0014, ADR-0020). Not scoped to a user: the token in the request is
how the user is found in the first place (see tests/test_repository_rule.py)."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core_api.db.models import AuthSession
from core_api.domain.auth.sessions import session_expiry, session_is_active
from core_api.domain.auth.tokens import hash_token, new_token

USER_AGENT_MAX = 256


class AuthSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, user_id: uuid.UUID, now: datetime, user_agent: str | None = None
    ) -> tuple[str, AuthSession]:
        """A new session with a new token (never reused: no session fixation). Return the raw
        token, for the client only, and the stored row."""
        raw, token_hash = new_token()
        row = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            last_seen_at=now,
            expires_at=session_expiry(now, now),
            user_agent=user_agent[:USER_AGENT_MAX] if user_agent else None,
        )
        self.session.add(row)
        self.session.flush()
        return raw, row

    def get_active(self, raw: str, now: datetime) -> AuthSession | None:
        """The live session of this token, or None if unknown, revoked or expired."""
        row = self.session.scalars(
            select(AuthSession).where(AuthSession.token_hash == hash_token(raw))
        ).one_or_none()
        if row is None or not session_is_active(
            row.created_at, row.expires_at, row.revoked_at, now
        ):
            return None
        return row

    def touch(self, row: AuthSession, now: datetime) -> None:
        """Slide the expiry: 30 more days from now, never past 90 days from sign-in."""
        row.last_seen_at = now
        row.expires_at = session_expiry(row.created_at, now)

    def revoke(self, row: AuthSession, now: datetime) -> None:
        if row.revoked_at is None:
            row.revoked_at = now

    def revoke_all(self, user_id: uuid.UUID, now: datetime) -> None:
        """End every live session of the user (logout-all, password reset)."""
        self.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
            .execution_options(synchronize_session="fetch")
        )
