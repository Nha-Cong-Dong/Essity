"""T8.3: two real connections writing one question's schedule (ADR-0029; US-06 AC7, US-16 AC11).
The question row is the lock: writers take turns, nothing is lost, and the result equals a replay.
The setup commits, so the teardown switches the guards off to remove the rows, as in
`tests/review/test_t215_draft_race.py` (T2.22 moves this to core_eraser)."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.db.models import PracticeLog, PracticeState
from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.practice import PracticeState as DomainState
from core_api.domain.scheduling.practice import replay_ratings
from core_api.repositories.practice import PracticeStateRepository
from core_api.repositories.user import UserRepository
from core_api.services.practice import record_grade, remove
from practice_rows import Practice, day
from races import finished, in_thread, wait_for_lock


@dataclass
class Ready:
    user_id: uuid.UUID
    question_id: uuid.UUID
    grade_ids: list[uuid.UUID]


@pytest.fixture
def ready(engine: Engine) -> Iterator[Ready]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t83-race-{uuid.uuid4()}@example.com")
        session.flush()
        practice = Practice(session, user)
        question = practice.question()
        # Two graded attempts waiting; nothing recorded yet, so the question has no state.
        grades = [practice.grade(practice.attempt(question, day(n)), "correct") for n in (0, 3)]
        made = Ready(user.id, question.id, [grade.id for grade in grades])
        session.commit()
    yield made
    with engine.begin() as connection:
        tables = connection.execute(
            text(
                "SELECT DISTINCT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE NOT t.tgisinternal AND n.nspname = 'public'"
            )
        ).scalars()
        names = list(tables)
        for name in names:
            connection.execute(text(f'ALTER TABLE "{name}" DISABLE TRIGGER USER'))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": made.user_id})
        for name in names:
            connection.execute(text(f'ALTER TABLE "{name}" ENABLE TRIGGER USER'))


def record(session: Session, ready: Ready, n: int) -> DomainState:
    return record_grade(
        session,
        ready.user_id,
        ready.question_id,
        ready.grade_ids[n],
        verdict="correct",
        active_seconds=100.0,
        reference_seconds=100.0,
        timing_ok=True,
    )


def stored(engine: Engine, ready: Ready) -> DomainState | None:
    with Session(engine) as check:
        return PracticeStateRepository(check, ready.user_id).state(ready.question_id)


def pid_of(session: Session) -> int:
    return session.execute(text("SELECT pg_backend_pid()")).scalar_one()


def counts(engine: Engine, user_id: uuid.UUID) -> tuple[int, int]:
    with Session(engine) as check:
        return (
            check.query(PracticeState).filter(PracticeState.user_id == user_id).count(),
            check.query(PracticeLog).filter(PracticeLog.user_id == user_id).count(),
        )


def test_two_first_attempts_at_once_serialise_to_one_state_row(
    engine: Engine, ready: Ready
) -> None:
    # Red when: two first attempts make two state rows, a UNIQUE error, or lose a log row.
    with Session(engine) as first, Session(engine) as second:
        record(first, ready, 0)
        pid = pid_of(second)
        thread, outcome = in_thread(lambda: record(second, ready, 1))
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        assert not isinstance(result, BaseException), result
        second.commit()
    assert counts(engine, ready.user_id) == (1, 2)
    expected = replay_ratings([(PracticeRating.GOOD, day(0)), (PracticeRating.GOOD, day(3))])
    assert expected is not None
    state = stored(engine, ready)
    assert state is not None
    assert state.memory == expected.memory


def seeded(engine: Engine, ready: Ready) -> None:
    with Session(engine) as seed:
        record(seed, ready, 0)
        seed.commit()


def test_remove_waits_for_a_recording_and_both_survive(engine: Engine, ready: Ready) -> None:
    # Red when: a remove racing a recording is lost, or the recording drops removed_at.
    seeded(engine, ready)
    with Session(engine) as first, Session(engine) as second:
        record(first, ready, 1)
        pid = pid_of(second)
        thread, outcome = in_thread(
            lambda: remove(second, ready.user_id, ready.question_id, day(4))
        )
        wait_for_lock(engine, pid, outcome)
        first.commit()
        assert finished(thread, outcome) is True
        second.commit()
    state = stored(engine, ready)
    assert state is not None
    assert state.removed_at == day(4)
    assert state.memory.last_review == day(3)
    assert counts(engine, ready.user_id) == (1, 2)


def test_recording_waits_for_a_remove_and_keeps_it(engine: Engine, ready: Ready) -> None:
    # Red when: a recording that waited for a remove overwrites removed_at with null.
    seeded(engine, ready)
    with Session(engine) as first, Session(engine) as second:
        assert remove(first, ready.user_id, ready.question_id, day(2))
        pid = pid_of(second)
        thread, outcome = in_thread(lambda: record(second, ready, 1))
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        assert not isinstance(result, BaseException), result
        second.commit()
    state = stored(engine, ready)
    assert state is not None
    assert state.removed_at == day(2)
    assert state.memory.last_review == day(3)


def test_whole_user_rebuild_waiting_on_a_remove_keeps_removed_at(
    engine: Engine, ready: Ready
) -> None:
    # Red when: a CLI rebuild racing remove reads removed_at before the remove and drops it.
    seeded(engine, ready)
    with Session(engine) as first, Session(engine) as second:
        assert remove(first, ready.user_id, ready.question_id, day(2))
        pid = pid_of(second)
        thread, outcome = in_thread(
            lambda: PracticeStateRepository(second, ready.user_id).rebuild()
        )
        wait_for_lock(engine, pid, outcome)
        first.commit()
        assert finished(thread, outcome) == 1
        second.commit()
    state = stored(engine, ready)
    assert state is not None
    assert state.removed_at == day(2)


def test_remove_waiting_on_a_whole_user_rebuild_is_not_lost(engine: Engine, ready: Ready) -> None:
    # Red when: a remove that waits behind a CLI rebuild finds the old row deleted and the new one
    # outside its snapshot, updates 0 rows and returns False: the learner's removal is lost
    # (task review Y1; the opposite order is covered above).
    seeded(engine, ready)
    with Session(engine) as first, Session(engine) as second:
        assert PracticeStateRepository(first, ready.user_id).rebuild() == 1
        pid = pid_of(second)
        thread, outcome = in_thread(
            lambda: remove(second, ready.user_id, ready.question_id, day(2))
        )
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        second.commit()
    assert result is True
    state = stored(engine, ready)
    assert state is not None
    assert state.removed_at == day(2)


def test_whole_user_rebuild_behind_a_recording_keeps_removed_at(
    engine: Engine, ready: Ready
) -> None:
    # Red when: a CLI rebuild that waited for a recording on a removed question misses the row
    # in its DELETE, inserts removed_at null, and the upsert writes that null over the removal.
    seeded(engine, ready)
    with Session(engine) as setup:
        assert remove(setup, ready.user_id, ready.question_id, day(1))
        setup.commit()
    with Session(engine) as first, Session(engine) as second:
        record(first, ready, 1)
        pid = pid_of(second)
        thread, outcome = in_thread(
            lambda: PracticeStateRepository(second, ready.user_id).rebuild()
        )
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        assert not isinstance(result, BaseException), result
        second.commit()
    state = stored(engine, ready)
    assert state is not None
    assert state.removed_at == day(1)
    assert state.memory.last_review == day(3)
    assert counts(engine, ready.user_id) == (1, 2)
