"""Accounts. The one repository not scoped to a user_id: it finds the user in the first place
(sign-up, login), so it holds no business data (see tests/test_repository_rule.py)."""

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models.user import DEFAULT_TIMEZONE, User
from core_api.domain.baseline import MAX_SKIPS
from core_api.domain.email import normalize_email


class EmailTakenError(Exception):
    """An account with this email already exists (compared after normalization)."""


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, email: str, password_hash: str | None = None, timezone: str = DEFAULT_TIMEZONE
    ) -> User:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone: {timezone!r}") from exc
        user = User(email=normalize_email(email), password_hash=password_hash, timezone=timezone)
        # A savepoint, so a duplicate email leaves the caller's transaction usable.
        try:
            with self.session.begin_nested():
                self.session.add(user)
        except IntegrityError as exc:
            raise EmailTakenError from exc
        return user

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalars(
            select(User).where(User.email == normalize_email(email))
        ).one_or_none()

    def record_baseline_skip(self, user_id: uuid.UUID) -> int:
        """Count one "Later" on the baseline screen, up to MAX_SKIPS (US-11 AC2). One statement,
        so a double click cannot count past the cap. Returns the count now stored."""
        self.session.execute(
            update(User)
            .where(User.id == user_id, User.baseline_skips < MAX_SKIPS)
            .values(baseline_skips=User.baseline_skips + 1)
            .execution_options(synchronize_session="fetch")
        )
        count = self.session.scalar(select(User.baseline_skips).where(User.id == user_id))
        return count or 0
