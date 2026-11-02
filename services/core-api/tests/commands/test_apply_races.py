"""T9.2c: two real connections apply commands at once (AC4): one row, no deadlock."""

import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from cmd_world import SESSION, CmdWorld, Parser
from core_api.db.models import User
from core_api.repositories.user import UserRepository
from core_api.services.commands import CommandRequest, CommandService


@pytest.fixture
def committed(engine: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """A committed user with a subject, one leaf section and one draft card."""
    with Session(engine, expire_on_commit=False) as setup:
        user: User = UserRepository(setup).create(f"race-{uuid.uuid4().hex[:8]}@example.com")
        setup.flush()
        world = CmdWorld(setup, user)
        ids = (user.id, world.leaf1.id, world.cards[0].id)
        setup.commit()
    try:
        yield ids
    finally:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE command_log DISABLE TRIGGER USER"))
            connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": ids[0]})
            connection.execute(text("ALTER TABLE command_log ENABLE TRIGGER USER"))


def apply_once(
    engine: Engine,
    user_id: uuid.UUID,
    command_id: uuid.UUID,
    ops: list[dict[str, object]],
    text_: str,
) -> object:
    with Session(engine, expire_on_commit=False) as session:
        try:
            out = CommandService(session, user_id).apply(
                command_id, SESSION, CommandRequest(text_), parse=Parser(ops)
            )
            session.commit()
            return out
        except BaseException as error:  # noqa: BLE001 - handed back to the test
            session.rollback()
            return error


def test_concurrent_same_command_id_single_row(
    engine: Engine, committed: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    user_id, leaf, _ = committed
    cid = uuid.uuid4()
    ops: list[dict[str, object]] = [{"kind": "section_exclude", "sections": [str(leaf)]}]
    with ThreadPoolExecutor(2) as pool:
        results = [
            f.result()
            for f in [pool.submit(apply_once, engine, user_id, cid, ops, "x") for _ in range(2)]
        ]
    assert all(not isinstance(r, BaseException) for r in results), results
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM command_log WHERE user_id = :u"), {"u": user_id}
        ).scalar_one()
    assert count == 1


def test_two_commands_same_card_no_deadlock(
    engine: Engine, committed: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    user_id, leaf, card = committed
    first: list[dict[str, object]] = [
        {"kind": "card_edit", "card": str(card), "text": "một"},
        {"kind": "section_exclude", "sections": [str(leaf)]},
    ]
    second: list[dict[str, object]] = [
        {"kind": "section_exclude", "sections": [str(leaf)]},
        {"kind": "card_edit", "card": str(card), "text": "hai"},
    ]
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(apply_once, engine, user_id, uuid.uuid4(), ops, "x")
            for ops in (first, second)
        ]
        results = [f.result(timeout=30) for f in futures]
    assert all(not isinstance(r, BaseException) for r in results), results
    with engine.connect() as connection:
        version = connection.execute(
            text("SELECT version FROM knowledge_unit WHERE id = :c"), {"c": card}
        ).scalar_one()
    assert version == 3  # both edits landed one after the other, neither overwrote blind
