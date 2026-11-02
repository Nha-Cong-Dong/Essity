"""T7.11 tester round 2: migration 0031 edges the branch test leaves open (feature-tester, 02/11).

Rows are committed (Alembic runs on its own connection) and removed in `finally`, whatever
the outcome, so the shared lane database keeps no residue."""

import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.db.models import User
from v2_rows import make_document, make_section, make_subject, make_unit


def _user(engine: Engine) -> uuid.UUID:
    user = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text('INSERT INTO "user" (id, email) VALUES (:u, :e)'),
            {"u": user, "e": f"{user}@example.com"},
        )
    return user


# US-03 AC4, plan D13 (backfill JOIN doc_section on id, subject and owner). Red when: an `active`
# card without a section stays `active` (the CHECK swap then fails), or a legacy `section_id` that
# names a section of another subject or of another user is copied (or makes the upgrade crash on
# the unit_section foreign key) instead of being skipped.
def test_0031_backfill_skips_sections_of_another_subject_or_owner(
    engine: Engine, alembic_cfg: Config
) -> None:
    alice, bob = _user(engine), _user(engine)
    try:
        with Session(engine) as s:
            a, b = s.get(User, alice), s.get(User, bob)
            assert a is not None and b is not None
            mine, other = make_subject(s, a), make_subject(s, a, name="Khác")
            theirs = make_subject(s, b)
            own = make_section(s, a, make_document(s, a, mine))
            other_subject = make_section(s, a, make_document(s, a, other, sha="cd" * 32))
            bobs = make_section(s, b, make_document(s, b, theirs))
            ok = make_unit(s, a, mine, section_id=own.id)
            bare = make_unit(s, a, mine)
            cross_subject = make_unit(s, a, mine, section_id=other_subject.id)
            cross_user = make_unit(s, a, mine, section_id=bobs.id)
            s.commit()
            units = [ok.id, bare.id, cross_subject.id, cross_user.id]
            own_id = own.id
        command.downgrade(alembic_cfg, "0030")
        with engine.begin() as c:
            c.execute(
                text("UPDATE knowledge_unit SET status = 'active' WHERE id = ANY(:ids)"),
                {"ids": units},
            )
            c.execute(text("DELETE FROM unit_section WHERE unit_id = ANY(:ids)"), {"ids": units})
        command.upgrade(alembic_cfg, "0031")
        with engine.connect() as c:
            got = dict(
                c.execute(
                    text("SELECT id, status FROM knowledge_unit WHERE id = ANY(:ids)"),
                    {"ids": units},
                )
                .tuples()
                .all()
            )
            links = (
                c.execute(
                    text("SELECT unit_id, section_id FROM unit_section WHERE unit_id = ANY(:ids)"),
                    {"ids": units},
                )
                .tuples()
                .all()
            )
        assert got == dict.fromkeys(units, "canonical")
        assert links == [(units[0], own_id)]
    finally:
        try:
            command.upgrade(alembic_cfg, "head")
        finally:
            with engine.begin() as c:
                c.execute(text('DELETE FROM "user" WHERE id IN (:a, :b)'), {"a": alice, "b": bob})
