"""T7.11, migration 0031: knowledge_unit.status active becomes canonical (US-03 AC4)."""

import uuid

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models import User
from v2_rows import World, make_document, make_section, make_subject, make_unit


def test_single_alembic_head(alembic_cfg: Config) -> None:
    # Red when: two migrations branch from the same parent.
    heads = ScriptDirectory.from_config(alembic_cfg).get_heads()
    assert len(heads) == 1


def test_check_drops_active_and_split(world: World) -> None:
    # Red when: `active` or `split` is still allowed after 0031.
    for status in ("active", "split"):
        with pytest.raises(IntegrityError), world.session.begin_nested():
            make_unit(world.session, world.alice, world.subject, status=status)
    for status in ("draft", "canonical", "merged", "retired"):
        make_unit(world.session, world.alice, world.subject, status=status)


def test_default_status_is_canonical(world: World) -> None:
    # Red when: the model default is still `active`.
    assert make_unit(world.session, world.alice, world.subject).status == "canonical"


def test_0031_up_down_data(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: old rows keep active/split, the section_id backfill is lost or takes an orphan id,
    # or downgrade changes data. Committed on purpose (Alembic runs on its own connection).
    user = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text('INSERT INTO "user" (id, email) VALUES (:u, :e)'),
            {"u": user, "e": f"{user}@example.com"},
        )
    with Session(engine) as s:
        owner = s.get(User, user)
        assert owner is not None
        subject = make_subject(s, owner)
        section = make_section(s, owner, make_document(s, owner, subject))
        ok = make_unit(s, owner, subject, section_id=section.id)
        split = make_unit(s, owner, subject)
        orphan = make_unit(s, owner, subject, section_id=uuid.uuid4())
        s.commit()
        ids = (ok.id, split.id, orphan.id, section.id)
    ok_id, split_id, orphan_id, section_id = ids
    try:
        command.downgrade(alembic_cfg, "0030")
        with engine.begin() as c:
            c.execute(
                text("UPDATE knowledge_unit SET status = 'active' WHERE id IN (:a, :b)"),
                {"a": ok_id, "b": orphan_id},
            )
            c.execute(
                text("UPDATE knowledge_unit SET status = 'split' WHERE id = :a"), {"a": split_id}
            )
            c.execute(text("DELETE FROM unit_section WHERE user_id = :u"), {"u": user})
        command.upgrade(alembic_cfg, "0031")
        with engine.connect() as c:
            got = dict(
                c.execute(
                    text("SELECT id, status FROM knowledge_unit WHERE user_id = :u"), {"u": user}
                )
                .tuples()
                .all()
            )
            links = (
                c.execute(
                    text("SELECT unit_id, section_id FROM unit_section WHERE user_id = :u"),
                    {"u": user},
                )
                .tuples()
                .all()
            )
        assert got == {ok_id: "canonical", split_id: "retired", orphan_id: "canonical"}
        assert links == [(ok_id, section_id)]
        command.downgrade(alembic_cfg, "0030")
        with engine.connect() as c:
            after = dict(
                c.execute(
                    text("SELECT id, status FROM knowledge_unit WHERE user_id = :u"), {"u": user}
                )
                .tuples()
                .all()
            )
        assert after == got
    finally:
        try:
            command.upgrade(alembic_cfg, "head")
        finally:
            with engine.begin() as c:
                c.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": user})
