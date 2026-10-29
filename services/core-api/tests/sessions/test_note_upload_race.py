"""Two note reservations of one user at once (T4.13b): the user row is the lock, so the quota
sum holds and only one of two that cannot both fit succeeds."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from session_helpers import subject_of
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.db.models import StudySession
from core_api.repositories.note_upload import NoteQuotaExceededError, NoteUploadRepository
from core_api.repositories.user import UserRepository
from races import finished, in_thread, wait_for_lock

MB = 1024 * 1024
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


@pytest.fixture
def committed(engine: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t413b-race-{uuid.uuid4()}@example.com")
        session.flush()
        subject = subject_of(session, user)
        draft = StudySession(subject_id=subject.id, description_raw="x", extraction="failed")
        draft.user_id = user.id
        session.add(draft)
        session.flush()
        ids = (user.id, draft.id)
        session.commit()
    yield ids
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": ids[0]})


def reserve(session: Session, user_id: uuid.UUID, session_id: uuid.UUID, n: int) -> None:
    NoteUploadRepository(session, user_id).reserve(
        session_id,
        sha256=f"{n:064x}",
        mime="image/jpeg",
        size_bytes=2 * MB,
        now=NOW,
        quota_bytes=3 * MB,
    )


def test_two_reservations_near_the_quota_let_one_through(
    engine: Engine, committed: tuple[uuid.UUID, uuid.UUID]
) -> None:
    # Red when: reserve sums the quota without holding the user row: both 2 MB would fit in 3 MB.
    user_id, session_id = committed
    with Session(engine) as first, Session(engine) as second:
        reserve(first, user_id, session_id, 1)
        second.execute(text("SET LOCAL lock_timeout = '15s'"))
        pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(lambda: reserve(second, user_id, session_id, 2))
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        second.rollback()
    assert isinstance(result, NoteQuotaExceededError), result
