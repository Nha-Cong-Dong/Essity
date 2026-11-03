"""T9.2b edges (tester): what two real connections at once, a row stored with its revisions, and the
downgraded guard must still do. The setup commits, so the teardown switches the guards off to
remove the rows, as in `tests/practice/test_practice_races.py`."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.repositories.command_log import CommandLogRepository
from core_api.repositories.study_filter import FilterState, StudyFilterRepository
from core_api.repositories.user import UserRepository
from erasure import erase_user
from races import finished, in_thread, wait_for_lock
from v2_rows import World, make_subject

HASH = "cd" * 32


@dataclass
class Ready:
    user_id: uuid.UUID
    subject_id: uuid.UUID
    command_id: uuid.UUID


@pytest.fixture
def ready(engine: Engine, eraser_engine: Engine) -> Iterator[Ready]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t92b-race-{uuid.uuid4()}@example.com")
        session.flush()
        subject = make_subject(session, user)
        row = CommandLogRepository(session, user.id).add_new(
            command_id=uuid.uuid4(),
            payload_hash=HASH,
            raw_text="bỏ chương 3",
            ops=[],
            inverse=[],
            affected_count=0,
            screen_session_id=uuid.uuid4(),
        )
        assert row is not None
        made = Ready(user.id, subject.id, row.command_id)
        session.commit()
    yield made
    erase_user(eraser_engine, made.user_id)


def pid_of(session: Session) -> int:
    return session.execute(text("SELECT pg_backend_pid()")).scalar_one()


def test_two_undos_at_once_flip_once_and_the_loser_gets_none(engine: Engine, ready: Ready) -> None:
    # Red when: mark_undone reads the row without FOR UPDATE: the second undo reads 'applied',
    # waits on the first one's UPDATE, then hits the guard (an error) instead of returning None.
    with Session(engine) as first, Session(engine) as second:
        assert CommandLogRepository(first, ready.user_id).mark_undone(ready.command_id)
        pid = pid_of(second)
        thread, outcome = in_thread(
            lambda: CommandLogRepository(second, ready.user_id).mark_undone(ready.command_id)
        )
        wait_for_lock(engine, pid, outcome)
        first.commit()
        assert finished(thread, outcome) is None
        second.rollback()


def test_same_command_id_at_once_one_row_and_the_loser_gets_none(
    engine: Engine, ready: Ready
) -> None:
    # Red when: a concurrent retry of one command_id makes a second row or raises (500) instead
    # of ON CONFLICT DO NOTHING handing back None after the first commits (AC4).
    shared = uuid.uuid4()

    def add(session: Session) -> object:
        return CommandLogRepository(session, ready.user_id).add_new(
            command_id=shared,
            payload_hash=HASH,
            raw_text="gộp thẻ",
            ops=[],
            inverse=[],
            affected_count=0,
        )

    with Session(engine) as first, Session(engine) as second:
        assert add(first) is not None
        pid = pid_of(second)
        thread, outcome = in_thread(lambda: add(second))
        wait_for_lock(engine, pid, outcome)
        first.commit()
        assert finished(thread, outcome) is None
        second.rollback()
    with Session(engine) as check:
        count = check.execute(
            text("SELECT count(*) FROM command_log WHERE user_id = :u AND command_id = :c"),
            {"u": ready.user_id, "c": shared},
        ).scalar_one()
    assert count == 1


def test_first_filter_of_a_subject_waits_on_the_lock_then_sees_rev_one(
    engine: Engine, ready: Ready
) -> None:
    # Red when: lock() takes no advisory lock while there is no row: the second writer does not
    # wait, reads rev 0 and its insert collides on the key (or a rev is lost).
    with Session(engine) as first, Session(engine) as second:
        filters = StudyFilterRepository(first, ready.user_id)
        assert filters.lock(ready.subject_id).rev == 0
        filters.set(ready.subject_id, "only", date(2026, 11, 9))
        pid = pid_of(second)

        def other() -> FilterState:
            repo = StudyFilterRepository(second, ready.user_id)
            seen = repo.lock(ready.subject_id)
            assert seen.rev == 1
            return repo.set(ready.subject_id, "defer", date(2026, 11, 10))

        thread, outcome = in_thread(other)
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        assert isinstance(result, FilterState), result
        assert (result.mode, result.rev) == ("defer", 2)
        second.commit()


def test_mark_undone_keeps_revisions_written_at_insert(world: World) -> None:
    # Red when: mark_undone overwrites undo_revs_json the apply already stored (the guard then
    # refuses the undo with an error instead of flipping the row).
    repo = CommandLogRepository(world.session, world.alice.id)
    row = repo.add_new(
        command_id=uuid.uuid4(),
        payload_hash=HASH,
        raw_text="x",
        ops=[],
        inverse=[],
        affected_count=0,
        undo_revs={"section:a": 2},
    )
    assert row is not None
    done = repo.mark_undone(row.command_id, undo_revs={"section:a": 7})
    assert done is not None
    assert (done.status, done.undo_revs_json) == ("undone", {"section:a": 2})


def test_downgrade_brings_back_a_working_0025_guard(
    engine: Engine, eraser_engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: the downgrade leaves the 0032 guard (it reads NEW.command_id, gone with the
    # column, so every undo fails) or a guard that lets a row change other than by undoing.
    user = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text('INSERT INTO "user" (id, email) VALUES (:u, :e)'),
            {"u": user, "e": f"{user}@example.com"},
        )
    try:
        command.downgrade(alembic_cfg, "0031")
        with engine.begin() as c:
            old = c.execute(
                text(
                    "INSERT INTO command_log (id, user_id, raw_text, ops_json, inverse_json,"
                    " affected_count) VALUES (gen_random_uuid(), :u, 'gộp', '[]', '[]', 0)"
                    " RETURNING id"
                ),
                {"u": user},
            ).scalar_one()
        with pytest.raises(Exception, match="refused"), engine.begin() as c:
            c.execute(text("UPDATE command_log SET raw_text = 'khác' WHERE id = :id"), {"id": old})
        with engine.begin() as c:
            c.execute(
                text("UPDATE command_log SET status = 'undone', undone_at = now() WHERE id = :id"),
                {"id": old},
            )
    finally:
        try:
            command.upgrade(alembic_cfg, "head")
        finally:
            erase_user(eraser_engine, user)
