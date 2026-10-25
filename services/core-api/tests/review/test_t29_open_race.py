"""Two tabs pressing "Bắt đầu" at once (T2.9 plan C4): the second insert waits on the partial
unique index, then reads the session the first one committed. Two real connections, so the setup
commits; the teardown switches the session guard off to remove it, as in
`test_t23_session_end_race.py` (T2.22 moves this to core_eraser)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.db.models import ReviewSession
from core_api.repositories.review import ReviewSessionRepository
from core_api.repositories.user import UserRepository
from races import finished, in_thread, wait_for_lock

NOW = datetime(2026, 11, 2, 13, 0, tzinfo=UTC)
DAY = date(2026, 11, 2)


@pytest.fixture
def user_id(engine: Engine) -> Iterator[uuid.UUID]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t29-race-{uuid.uuid4()}@example.com")
        session.commit()
        made = user.id
    yield made
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE review_session DISABLE TRIGGER review_session_guard"))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": made})
        connection.execute(text("ALTER TABLE review_session ENABLE TRIGGER review_session_guard"))


# Red when: the index or the ON CONFLICT is missing, so both tabs make a session (or the second
# fails with a unique violation instead of reading the first).
def test_t29_two_tabs_get_one_session(engine: Engine, user_id: uuid.UUID) -> None:
    with Session(engine) as first, Session(engine) as second:
        made, created = ReviewSessionRepository(first, user_id).open_for_day(DAY, NOW)
        assert created
        pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(
            lambda: ReviewSessionRepository(second, user_id).open_for_day(DAY, NOW)
        )
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        assert not isinstance(result, BaseException), result
        found, created_again = result  # type: ignore[misc]
        assert (found.id, created_again) == (made.id, False)  # type: ignore[union-attr]
        second.commit()
    with Session(engine) as check:
        count = check.query(ReviewSession).filter(ReviewSession.user_id == user_id).count()
    assert count == 1
