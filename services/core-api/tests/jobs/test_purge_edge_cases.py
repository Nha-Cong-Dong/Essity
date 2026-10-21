"""T1.9 edge cases found by the independent tester.

`test_purge_unverified.py` builds its ages from `UNVERIFIED_LIFETIME`, so a wrong constant (6 or
8 days) passes it. These tests use literal days and the exact boundary.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from core_api.db.models import User
from core_api.jobs.purge_unverified import UNVERIFIED_LIFETIME, purge_unverified
from core_api.repositories.user import UserRepository

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def unverified(session: Session, age: timedelta) -> User:
    user = UserRepository(session).create(f"edge-{uuid.uuid4().hex[:12]}@example.com")
    user.created_at = NOW - age
    session.flush()
    return user


def alive(session: Session, user_id: uuid.UUID) -> bool:
    session.expire_all()
    return session.get(User, user_id) is not None


def test_unverified_lifetime_is_7_days() -> None:
    """Catches: the constant changed to 6 or 8 days (ADR-0020 §4 says 7)."""
    assert UNVERIFIED_LIFETIME == timedelta(days=7)


def test_purge_6_days_23_hours_kept_7_days_1_hour_deleted(db_session: Session) -> None:
    """Catches: lifetime 6 days (the first is wrongly deleted) or 8 days (the second is kept)."""
    young = unverified(db_session, timedelta(days=6, hours=23)).id
    old = unverified(db_session, timedelta(days=7, hours=1)).id
    purge_unverified(db_session, NOW)
    assert alive(db_session, young)
    assert not alive(db_session, old)


def test_purge_exactly_7_days_old_is_kept(db_session: Session) -> None:
    """Catches: `<` turned into `<=` (a 7-day-old account is deleted one tick early)."""
    boundary = unverified(db_session, timedelta(days=7)).id
    purge_unverified(db_session, NOW)
    assert alive(db_session, boundary)


def test_purge_twice_is_harmless(db_session: Session) -> None:
    """Catches: a second run raising or deleting more (idempotence, ADR-0020 §4)."""
    old = unverified(db_session, timedelta(days=30)).id
    assert purge_unverified(db_session, NOW) >= 1
    assert purge_unverified(db_session, NOW) == 0
    assert not alive(db_session, old)
