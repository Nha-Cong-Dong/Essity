"""Fixed now for the stats and export routes (R23)."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from core_api.api.deps import get_now
from core_api.db.models import User
from core_api.main import app
from practice_rows import Practice

# 15:00 in Ho Chi Minh City on 20 October 2026: learning day 20 October.
NOW = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def set_now() -> Iterator[Callable[[datetime], None]]:
    current = [NOW]
    app.dependency_overrides[get_now] = lambda: current[0]
    yield lambda instant: current.__setitem__(0, instant)
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def practice(db_session: Session, two_users: tuple[User, User]) -> Practice:
    return Practice(db_session, two_users[0])
