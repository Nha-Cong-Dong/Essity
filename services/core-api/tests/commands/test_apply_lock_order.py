"""T9.2c lock order (plan T9.2c, R2-Y2): a command takes its locks in the screens' order,
document before its sections, study session before its cards, sections before questions. Another
connection holds the first lock of a pair; while the command waits on it, the second row must
still be free (else the command holds B and waits for A: a deadlock with the screen that holds A
and wants B).
"""

import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from cmd_world import SESSION, CmdWorld, Parser
from core_api.db.models import User
from core_api.repositories.user import UserRepository
from core_api.services.commands import ApplyOutcome, CommandRequest, CommandService


@dataclass(frozen=True)
class Ids:
    user: uuid.UUID
    document: uuid.UUID
    leaf: uuid.UUID
    study: uuid.UUID
    card: uuid.UUID
    question: uuid.UUID


@pytest.fixture
def world(engine: Engine) -> Iterator[Ids]:
    with Session(engine, expire_on_commit=False) as setup:
        user: User = UserRepository(setup).create(f"lock-{uuid.uuid4().hex[:8]}@example.com")
        setup.flush()
        w = CmdWorld(setup, user)
        ids = Ids(user.id, w.document.id, w.leaf1.id, w.study.id, w.cards[0].id, w.questions[0].id)
        setup.commit()
    try:
        yield ids
    finally:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE command_log DISABLE TRIGGER USER"))
            connection.execute(text("ALTER TABLE practice_removal_log DISABLE TRIGGER USER"))
            connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": ids.user})
            connection.execute(text("ALTER TABLE practice_removal_log ENABLE TRIGGER USER"))
            connection.execute(text("ALTER TABLE command_log ENABLE TRIGGER USER"))


def apply_once(engine: Engine, user_id: uuid.UUID, ops: list[dict[str, object]]) -> object:
    with Session(engine, expire_on_commit=False) as session:
        try:
            out = CommandService(session, user_id).apply(
                uuid.uuid4(), SESSION, CommandRequest("x"), parse=Parser(ops)
            )
            session.commit()
            return out
        except BaseException as error:  # noqa: BLE001 - handed back to the test
            session.rollback()
            return error


def wait_for_lock_wait(engine: Engine, pid_holder: int) -> None:
    """Until some backend of this database waits on a lock held by `pid_holder`."""
    deadline = time.monotonic() + 10
    with engine.connect() as probe:
        while time.monotonic() < deadline:
            waiting = probe.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND :p = ANY(pg_blocking_pids(pid))"
                ),
                {"p": pid_holder},
            ).scalar_one()
            if waiting:
                return
            probe.rollback()
            time.sleep(0.05)
    raise AssertionError("the command never waited on the held lock")


def is_free(engine: Engine, table: str, id_: uuid.UUID) -> bool:
    with engine.connect() as probe:
        try:
            probe.execute(
                text(f"SELECT 1 FROM {table} WHERE id = :i FOR UPDATE NOWAIT"),  # noqa: S608
                {"i": id_},
            )
            return True
        except OperationalError:
            return False
        finally:
            probe.rollback()


def hold(holder: Connection, table: str, id_: uuid.UUID) -> int:
    holder.execute(text(f"SELECT 1 FROM {table} WHERE id = :i FOR UPDATE"), {"i": id_})  # noqa: S608
    return holder.execute(text("SELECT pg_backend_pid()")).scalar_one()


def check(
    engine: Engine,
    ids: Ids,
    held: tuple[str, uuid.UUID],
    probe: tuple[str, uuid.UUID],
    ops: list[dict[str, object]],
) -> tuple[bool, object]:
    """Hold `held`, start the command, and once it waits report whether `probe` is free."""
    with engine.connect() as holder, ThreadPoolExecutor(1) as pool:
        holder.begin()
        pid = hold(holder, *held)
        future = pool.submit(apply_once, engine, ids.user, ops)
        try:
            wait_for_lock_wait(engine, pid)
            free = is_free(engine, *probe)
        finally:
            holder.rollback()
        return free, future.result(timeout=30)


def test_document_before_its_sections(engine: Engine, world: Ids) -> None:
    # Red when: the command locks the document's sections before the document (OutlineService
    # takes document then section: the two would deadlock).
    ops: list[dict[str, object]] = [{"kind": "section_exclude", "sections": [str(world.leaf)]}]
    free, result = check(
        engine, world, ("document", world.document), ("doc_section", world.leaf), ops
    )
    assert free and not isinstance(result, BaseException), result


def test_study_session_before_its_cards(engine: Engine, world: Ids) -> None:
    # Red when: the command locks the card before its study session (the review screen locks the
    # session, then its drafts).
    ops: list[dict[str, object]] = [{"kind": "card_edit", "card": str(world.card), "text": "mới"}]
    free, result = check(
        engine, world, ("study_session", world.study), ("knowledge_unit", world.card), ops
    )
    assert free and not isinstance(result, BaseException), result


def test_sections_before_questions(engine: Engine, world: Ids) -> None:
    # Red when: the command locks the question before the sections (order doc_section < question).
    ops: list[dict[str, object]] = [
        {"kind": "question_set_answer", "question": str(world.question), "text": "đáp"},
        {"kind": "section_exclude", "sections": [str(world.leaf)]},
    ]
    free, result = check(
        engine, world, ("question", world.question), ("doc_section", world.leaf), ops
    )
    assert not free and not isinstance(result, BaseException), result


def test_question_read_after_its_lock(engine: Engine, world: Ids) -> None:
    # Red when: the command loads the question before locking it: a screen's answer committed
    # while the command waits is missing from the inverse, and an undo would wipe it out.
    ops: list[dict[str, object]] = [
        {"kind": "question_set_answer", "question": str(world.question), "text": "lệnh"}
    ]
    with engine.connect() as holder, ThreadPoolExecutor(1) as pool:
        holder.begin()
        holder.execute(
            text("UPDATE question SET answer_text = 'tay', answer_origin = 'user' WHERE id = :q"),
            {"q": world.question},
        )
        pid = holder.execute(text("SELECT pg_backend_pid()")).scalar_one()
        future = pool.submit(apply_once, engine, world.user, ops)
        wait_for_lock_wait(engine, pid)
        holder.commit()
        result = future.result(timeout=30)
    assert isinstance(result, ApplyOutcome), result
    assert result.diff[0]["before"]["answer"] == "tay"


def test_card_add_does_not_deadlock_with_a_screen_insert_under_a_sibling(
    engine: Engine, world: Ids
) -> None:
    # Red when: the command locks the document's sections FOR UPDATE: the review screen holds its
    # study session, then takes KEY SHARE on a section (the foreign key of a new card), and the
    # two wait for each other (final review O1).
    ops: list[dict[str, object]] = [
        {"kind": "card_add", "section": str(world.leaf), "text": "thẻ mới"}
    ]
    with engine.connect() as screen, ThreadPoolExecutor(1) as pool:
        screen.begin()
        pid = hold(screen, "study_session", world.study)
        sibling = screen.execute(
            text("SELECT id FROM doc_section WHERE id <> :l AND user_id = :u LIMIT 1"),
            {"l": world.leaf, "u": world.user},
        ).scalar_one()
        future = pool.submit(apply_once, engine, world.user, ops)
        wait_for_lock_wait(engine, pid)
        screen.execute(
            text("SELECT 1 FROM doc_section WHERE id = :i FOR KEY SHARE"), {"i": sibling}
        )
        screen.commit()
        result = future.result(timeout=30)
    assert isinstance(result, ApplyOutcome), result
