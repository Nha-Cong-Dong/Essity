"""Accounts. The one repository not scoped to a user_id: it finds the user in the first place
(sign-up, login), so it holds no business data (see tests/test_repository_rule.py)."""

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models.user import DEFAULT_TIMEZONE, User
from core_api.domain.auth.username import normalize_username, username_from_email
from core_api.domain.email import normalize_email


class EmailTakenError(Exception):
    """An account with this email already exists (compared after normalization)."""


class UsernameTakenError(Exception):
    """An account with this username already exists (compared after normalization)."""


def _violated(exc: IntegrityError) -> str | None:
    """Name of the constraint a failed INSERT broke (PostgreSQL), if the driver says."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        email: str,
        password_hash: str | None = None,
        timezone: str = DEFAULT_TIMEZONE,
        *,
        username: str | None = None,
        display_name: str | None = None,
    ) -> User:
        """Insert the account. `username` and `display_name` must already be validated and
        normalized by the caller (domain.auth); without a username one is made from the email
        (accounts that did not choose one: tests, and Google sign-in later)."""
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown time zone: {timezone!r}") from exc
        email = normalize_email(email)
        if username is not None:
            return self._insert(email, password_hash, timezone, username, display_name)
        taken: set[str] = set()
        while True:
            candidate = username_from_email(email, taken)
            try:
                return self._insert(email, password_hash, timezone, candidate, display_name)
            except UsernameTakenError:
                taken.add(candidate)

    def _insert(
        self,
        email: str,
        password_hash: str | None,
        timezone: str,
        username: str,
        display_name: str | None,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            timezone=timezone,
            username=username,
            display_name=display_name,
        )
        # A savepoint, so a duplicate leaves the caller's transaction usable.
        try:
            with self.session.begin_nested():
                self.session.add(user)
        except IntegrityError as exc:
            name = _violated(exc)
            if name == "uq_user_email":
                raise EmailTakenError from exc
            if name == "uq_user_username":
                raise UsernameTakenError from exc
            raise  # a CHECK or NOT NULL: a bug in the caller, never "taken"
        return user

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalars(
            select(User).where(User.email == normalize_email(email))
        ).one_or_none()

    def get_by_username(self, username: str) -> User | None:
        return self.session.scalars(
            select(User).where(User.username == normalize_username(username))
        ).one_or_none()

    def username_taken(self, username: str) -> bool:
        return self.get_by_username(username) is not None
