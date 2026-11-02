"""T9.2d: an undo against real concurrent connections (AC5): a screen edit that lands first wins,
two undos of one command flip it once, and an undo and an apply do not deadlock."""

import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_apply_races import committed as committed  # noqa: F401  (fixture)

from cmd_world import SESSION, CmdWorld, Parser
from core_api.db.models import CommandLog, DocSection, Question
from core_api.domain.commands.registry import CommandRejected
from core_api.repositories.practice_removal import PracticeRemovalRepository
from core_api.repositories.user import UserRepository
from core_api.services import practice
from core_api.services.commands import CommandRequest, CommandService, UndoOutcome
from core_api.services.outline import OutlineService
from races import finished, in_thread, wait_for_lock

Committed = tuple[uuid.UUID, uuid.UUID, uuid.UUID]


def apply_committed(
    engine: Engine, user_id: uuid.UUID, ops: list[dict[str, object]], session_id: uuid.UUID
) -> uuid.UUID:
    cid = uuid.uuid4()
    with Session(engine, expire_on_commit=False) as session:
        CommandService(session, user_id).apply(
            cid, session_id, CommandRequest("x"), parse=Parser(ops)
        )
        session.commit()
    return cid


def undo_once(engine: Engine, user_id: uuid.UUID, cid: uuid.UUID) -> object:
    with Session(engine, expire_on_commit=False) as session:
        try:
            out = CommandService(session, user_id).undo(cid)
            session.commit()
            return out
        except BaseException as error:  # noqa: BLE001 - handed back to the test
            session.rollback()
            return error


def test_ac5_undo_race_with_manual_edit_one_409(engine: Engine, committed: Committed) -> None:
    user_id, leaf1, _ = committed
    cid = apply_committed(
        engine, user_id, [{"kind": "section_exclude", "sections": [str(leaf1)]}], SESSION
    )
    with Session(engine, expire_on_commit=False) as screen:
        OutlineService(screen, user_id).edit_section(leaf1, studied=True)  # holds the document
        pids: list[int] = []

        def undo() -> object:
            with Session(engine, expire_on_commit=False) as own:
                pids.append(own.execute(text("SELECT pg_backend_pid()")).scalar_one())
                try:
                    return CommandService(own, user_id).undo(cid)
                finally:
                    own.rollback()

        thread, outcome = in_thread(undo)
        while not pids:
            thread.join(0.05)
        wait_for_lock(engine, pids[0], outcome)  # the undo waits for the screen's lock
        screen.commit()
    result = finished(thread, outcome)
    assert isinstance(result, CommandRejected) and result.code == "changed_after", result
    with Session(engine) as check:
        leaf = check.get(DocSection, leaf1)
        row = check.scalars(select(CommandLog).where(CommandLog.command_id == cid)).one()
        assert leaf is not None and leaf.excluded is True and leaf.studied_weight == leaf.weight
        assert row.status == "applied"


def test_ac5_two_undos_of_one_command_flip_it_once(engine: Engine, committed: Committed) -> None:
    user_id, leaf1, _ = committed
    cid = apply_committed(
        engine, user_id, [{"kind": "section_exclude", "sections": [str(leaf1)]}], SESSION
    )
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(undo_once, engine, user_id, cid) for _ in range(2)]
        results = [f.result(30) for f in futures]
    assert not [r for r in results if isinstance(r, BaseException)], results
    assert sorted(isinstance(r, UndoOutcome) and r.replayed for r in results) == [False, True]
    with Session(engine) as check:
        leaf = check.get(DocSection, leaf1)
        assert leaf is not None and leaf.excluded is False


def test_apply_vs_undo_lock_order_no_deadlock(engine: Engine, committed: Committed) -> None:
    user_id, leaf1, _ = committed
    with Session(engine) as lookup:
        question = lookup.scalars(select(Question.id).where(Question.user_id == user_id)).first()
    if question is None:  # the fixture's world has questions; keep the test honest if it changes
        raise AssertionError("no question in the world")
    first = apply_committed(
        engine,
        user_id,
        [
            {"kind": "section_exclude", "sections": [str(leaf1)]},
            {"kind": "question_set_answer", "question": str(question), "text": "một"},
        ],
        SESSION,
    )
    other = uuid.uuid4()
    ops: list[dict[str, object]] = [  # the other order of the same two rows
        {"kind": "question_set_answer", "question": str(question), "text": "hai"},
        {"kind": "section_mark", "sections": [str(leaf1)], "studied": True},
    ]

    def apply_other() -> object:
        with Session(engine, expire_on_commit=False) as session:
            try:
                out = CommandService(session, user_id).apply(
                    uuid.uuid4(), other, CommandRequest("x"), parse=Parser(ops)
                )
                session.commit()
                return out
            except BaseException as error:  # noqa: BLE001 - handed back to the test
                session.rollback()
                return error

    with ThreadPoolExecutor(2) as pool:
        undo_future = pool.submit(undo_once, engine, user_id, first)
        apply_future = pool.submit(apply_other)
        results = [undo_future.result(30), apply_future.result(30)]
    assert not [r for r in results if isinstance(r, OperationalError)], results
    for r in results:
        assert not isinstance(r, BaseException) or isinstance(r, CommandRejected), r


@pytest.fixture
def committed_practice(engine: Engine) -> Iterator[Committed]:
    """`committed`, whose cleanup also lets the append-only practice log go."""
    with Session(engine, expire_on_commit=False) as setup:
        user = UserRepository(setup).create(f"race-{uuid.uuid4().hex[:8]}@example.com")
        setup.flush()
        world = CmdWorld(setup, user)
        ids = (user.id, world.leaf1.id, world.cards[0].id)
        setup.commit()
    try:
        yield ids
    finally:
        with engine.begin() as connection:
            for table in ("command_log", "practice_removal_log"):
                connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
            connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": ids[0]})
            for table in ("command_log", "practice_removal_log"):
                connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))


def test_ac5_undo_practice_waits_for_screen_and_sees_its_rev(
    engine: Engine, committed_practice: Committed
) -> None:  # F2, AC5 (tester T9.2d)
    # Red when: the undo reads the practice rev before it holds the question row (lock set
    # without the question of a practice_removal revert, or no lock at all): the screen's
    # readd + remove commit while the undo waits inside readd, and the undo puts the question back
    # over the user's own removal.
    user_id, _, _ = committed_practice
    with Session(engine) as lookup:
        question = lookup.scalars(select(Question.id).where(Question.user_id == user_id)).first()
    assert question is not None
    cid = apply_committed(
        engine,
        user_id,
        [{"kind": "question_remove_from_practice", "question": str(question)}],
        SESSION,
    )
    with Session(engine, expire_on_commit=False) as screen:
        practice.readd(screen, user_id, question)  # holds the question row
        practice.remove(screen, user_id, question, at=datetime.now(UTC))
        pids: list[int] = []

        def undo() -> object:
            with Session(engine, expire_on_commit=False) as own:
                pids.append(own.execute(text("SELECT pg_backend_pid()")).scalar_one())
                try:
                    out = CommandService(own, user_id).undo(cid)
                    own.commit()
                    return out
                except BaseException as error:  # noqa: BLE001 - handed back to the test
                    own.rollback()
                    return error

        thread, outcome = in_thread(undo)
        while not pids:
            thread.join(0.05)
        wait_for_lock(engine, pids[0], outcome)
        screen.commit()
    result = finished(thread, outcome)
    assert isinstance(result, CommandRejected) and result.code == "changed_after", result
    with Session(engine) as check:
        assert not PracticeRemovalRepository(check, user_id).in_practice(question)
