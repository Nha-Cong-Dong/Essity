"""T9.2c: a command waits for a screen edit of the same outline (document lock first), then both
land; neither overwrites the other and nothing deadlocks (plan: lock order, AC4)."""

import uuid

from cmd_world import SESSION, Parser
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session
from test_apply_races import committed as committed  # noqa: F401  (fixture)

from core_api.db.models import DocSection
from core_api.services.commands import CommandRequest, CommandService
from core_api.services.outline import OutlineService
from races import finished, in_thread, wait_for_lock


def test_ac4_apply_waits_for_outline_edit_then_both_land(
    engine: Engine, committed: tuple[uuid.UUID, uuid.UUID, uuid.UUID]
) -> None:
    user_id, leaf1, _ = committed
    with Session(engine, expire_on_commit=False) as screen:
        leaf2 = screen.scalars(
            select(DocSection.id).where(DocSection.user_id == user_id, DocSection.title == "1.2")
        ).one()
        OutlineService(screen, user_id).edit_section(leaf2, excluded=True)  # holds the document
        pids: list[int] = []

        def command() -> object:
            with Session(engine, expire_on_commit=False) as own:
                pids.append(own.execute(text("SELECT pg_backend_pid()")).scalar_one())
                out = CommandService(own, user_id).apply(
                    uuid.uuid4(),
                    SESSION,
                    CommandRequest("x"),
                    parse=Parser([{"kind": "section_exclude", "sections": [str(leaf1)]}]),
                )
                own.commit()
                return out

        thread, outcome = in_thread(command)
        while not pids:
            thread.join(0.05)
        wait_for_lock(engine, pids[0], outcome)
        screen.commit()
    result = finished(thread, outcome)
    assert not isinstance(result, BaseException), result
    with engine.connect() as connection:
        excluded = connection.execute(
            text("SELECT count(*) FROM doc_section WHERE user_id = :u AND excluded"),
            {"u": user_id},
        ).scalar_one()
    assert excluded == 2
