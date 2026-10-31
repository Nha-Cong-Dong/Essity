"""T7.M3, migration 0027 (ADR-0008, additions only; PLAN T7.8): draft cards of a session
(`knowledge_unit.session_id`, `draft_key`), `retired_at`, `saved_at`/`saved_learning_day`, the
`study_ledger` table, `unit.saved.v1` in the outbox, and the submission retry columns."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from core_api.db.models import KnowledgeUnit, Outbox, StudyLedger, Submission
from v2_rows import (
    NOW,
    World,
    make_study_session,
    make_subject,
    make_unit,
)

UNIT_COLUMNS = {"session_id", "draft_key", "retired_at", "saved_at", "saved_learning_day"}
SUBMISSION_COLUMNS = {"retry_count", "next_attempt_at"}
DAY = date(2026, 11, 1)


def columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                {"t": table},
            ).scalars()
        )


def test_single_alembic_head(alembic_cfg: Config) -> None:
    # Red when: two migrations branch from the same parent, or 0027 is not the head.
    assert ScriptDirectory.from_config(alembic_cfg).get_heads() == ["0027"]


def test_0027_round_trip(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: a column or table is left behind or missing after 0026->0027->0026->0027.
    try:
        command.downgrade(alembic_cfg, "0026")
        assert not UNIT_COLUMNS & columns(engine, "knowledge_unit")
        assert not SUBMISSION_COLUMNS & columns(engine, "submission")
        assert not columns(engine, "study_ledger")
    finally:
        command.upgrade(alembic_cfg, "head")
    assert UNIT_COLUMNS <= columns(engine, "knowledge_unit")
    assert SUBMISSION_COLUMNS <= columns(engine, "submission")
    assert columns(engine, "study_ledger")


def test_models_match_the_migrated_database(engine: Engine) -> None:
    # Red when: a model differs from what 0027 built (type, nullability, index, unique).
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from core_api.db.base import Base
    from core_api.db.models import __all__ as _  # noqa: F401

    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diff = [
            item
            for item in compare_metadata(context, Base.metadata)
            if "procrastinate" not in repr(item)
            and any(n in repr(item) for n in ("study_ledger", "knowledge_unit", "submission"))
        ]
    assert diff == []


def test_check_names_match_the_database(engine: Engine) -> None:
    # Red when: a CHECK of the new columns differs by name (compare_metadata skips CHECKs).
    from core_api.db.base import Base
    from core_api.db.models import __all__ as _  # noqa: F401

    wanted = {
        str(c.name)
        for t in ("knowledge_unit", "submission", "study_ledger")
        for c in Base.metadata.tables[t].constraints
        if str(c.name).startswith("ck_")
    }
    with engine.connect() as connection:
        built = set(
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE contype = 'c' AND conrelid IN"
                    " ('knowledge_unit'::regclass, 'submission'::regclass,"
                    " 'study_ledger'::regclass)"
                )
            ).scalars()
        )
    assert wanted and wanted <= built


def add(world: World, row: Any) -> Any:
    world.session.add(row)
    world.session.flush()
    return row


def refused(world: World, row: Any) -> None:
    with pytest.raises(IntegrityError), world.session.begin_nested():
        add(world, row)


# --- knowledge_unit ----------------------------------------------------------------------------


def test_unit_may_belong_to_a_session_with_a_draft_key(world: World) -> None:
    study = make_study_session(world.session, world.alice, world.subject)
    unit = make_unit(
        world.session, world.alice, world.subject, session_id=study.id, draft_key="k" * 64
    )
    assert unit.draft_key == "k" * 64


def test_old_units_need_no_session_or_dates(world: World) -> None:
    # Red when: a new column is NOT NULL (seeded and v1 cards have none).
    unit = make_unit(world.session, world.alice, world.subject)
    assert unit.session_id is None and unit.retired_at is None and unit.saved_at is None


def test_draft_key_is_unique_per_session_but_not_across_sessions(world: World) -> None:
    # Red when: the partial unique (session_id, draft_key) is missing, or is global.
    one = make_study_session(world.session, world.alice, world.subject)
    two = make_study_session(world.session, world.alice, world.subject)
    make_unit(world.session, world.alice, world.subject, session_id=one.id, draft_key="a")
    make_unit(world.session, world.alice, world.subject, session_id=two.id, draft_key="a")
    with pytest.raises(IntegrityError), world.session.begin_nested():
        make_unit(world.session, world.alice, world.subject, session_id=one.id, draft_key="a")


def test_two_units_of_a_session_without_a_key_are_fine(world: World) -> None:
    # Red when: the unique index covers NULL keys.
    study = make_study_session(world.session, world.alice, world.subject)
    for _ in range(2):
        make_unit(world.session, world.alice, world.subject, session_id=study.id)


def test_unit_cannot_point_at_another_users_session(world: World) -> None:
    # Red when: the key to study_session is on id alone.
    bobs = make_study_session(
        world.session, world.bob, make_subject(world.session, world.bob, "Của Bob")
    )
    with pytest.raises(IntegrityError), world.session.begin_nested():
        make_unit(world.session, world.alice, world.subject, session_id=bobs.id)


def test_deleting_a_session_keeps_its_units(world: World) -> None:
    # Red when: the key cascades (a unit may be reviewed: review_log points at it) or blocks.
    study = make_study_session(world.session, world.alice, world.subject)
    unit = make_unit(world.session, world.alice, world.subject, session_id=study.id, draft_key="a")
    world.session.execute(text("DELETE FROM study_session WHERE id = :i"), {"i": study.id})
    world.session.expire_all()
    kept = world.session.get(KnowledgeUnit, unit.id)
    assert kept is not None and kept.session_id is None and kept.user_id == world.alice.id


def test_retired_at_only_on_retired_units(world: World) -> None:
    # Red when: CHECK retired_at IS NULL OR status = 'retired' is missing; old 'retired' rows
    # without a time stay valid.
    make_unit(world.session, world.alice, world.subject, status="retired")
    make_unit(world.session, world.alice, world.subject, status="retired", retired_at=NOW)
    with pytest.raises(IntegrityError), world.session.begin_nested():
        make_unit(world.session, world.alice, world.subject, status="active", retired_at=NOW)


@pytest.mark.parametrize("values", [{"saved_at": NOW}, {"saved_learning_day": DAY}])
def test_saved_at_and_day_come_together(world: World, values: dict[str, Any]) -> None:
    # Red when: the both-or-neither CHECK on saved_at / saved_learning_day is missing.
    with pytest.raises(IntegrityError), world.session.begin_nested():
        make_unit(world.session, world.alice, world.subject, **values)
    make_unit(
        world.session,
        world.alice,
        world.subject,
        status="draft",
        saved_at=NOW,
        saved_learning_day=DAY,
    )


# --- study_ledger ------------------------------------------------------------------------------


def ledger(world: World, study_id: uuid.UUID, **kw: Any) -> StudyLedger:
    values: dict[str, Any] = {
        "user_id": world.alice.id,
        "subject_id": world.subject.id,
        "session_id": study_id,
        "learning_day": DAY,
        "section_id": None,
        "units_saved": 1,
    }
    values.update(kw)
    return StudyLedger(**values)


def test_ledger_row_has_defaults(world: World) -> None:
    study = make_study_session(world.session, world.alice, world.subject)
    row = add(world, ledger(world, study.id))
    assert row.created_at is not None and row.updated_at is not None


def test_ledger_unique_per_session_day_section_even_without_a_section(world: World) -> None:
    # Red when: UNIQUE (session_id, learning_day, section_id) treats NULL sections as distinct.
    study = make_study_session(world.session, world.alice, world.subject)
    add(world, ledger(world, study.id))
    refused(world, ledger(world, study.id))
    section = uuid.uuid4()
    add(world, ledger(world, study.id, section_id=section))
    refused(world, ledger(world, study.id, section_id=section))
    add(world, ledger(world, study.id, learning_day=date(2026, 11, 2)))


def test_ledger_units_saved_not_negative(world: World) -> None:
    study = make_study_session(world.session, world.alice, world.subject)
    refused(world, ledger(world, study.id, units_saved=-1))
    add(world, ledger(world, study.id, units_saved=0))


def test_ledger_session_must_be_the_users(world: World) -> None:
    # Red when: the key to study_session is on id alone (the subject follows the session in code).
    bobs = make_study_session(
        world.session, world.bob, make_subject(world.session, world.bob, "Của Bob")
    )
    refused(world, ledger(world, bobs.id))


# --- outbox and submission ---------------------------------------------------------------------


def outbox(event_type: str, user_id: uuid.UUID) -> Outbox:
    return Outbox(
        id=uuid.uuid4(),
        user_id=user_id,
        event_type=event_type,
        payload={},
        trace_context={},
        occurred_at=datetime(2026, 11, 1, tzinfo=UTC),
        available_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


def test_outbox_accepts_unit_saved_and_still_refuses_unknown(world: World) -> None:
    # Red when: 'unit.saved.v1' is left out of ck_outbox_event_type, or the CHECK is dropped.
    add(world, outbox("unit.saved.v1", world.alice.id))
    refused(world, outbox("unit.saved.v2", world.alice.id))


def test_submission_retry_columns(world: World) -> None:
    study = make_study_session(world.session, world.alice, world.subject)
    row = add(world, Submission(user_id=world.alice.id, session_id=study.id, status="queued"))
    world.session.refresh(row)
    assert row.retry_count == 0 and row.next_attempt_at is None
    refused(
        world,
        Submission(user_id=world.alice.id, session_id=study.id, status="queued", retry_count=-1),
    )


# --- downgrade ---------------------------------------------------------------------------------


def test_downgrade_refuses_while_a_saved_event_is_in_the_outbox(
    engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: the downgrade narrows the outbox CHECK over a unit.saved.v1 row, or deletes it.
    # Committed on purpose (Alembic runs on its own connection) and removed in `finally`.
    user_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text('INSERT INTO "user" (id, email) VALUES (:i, :e)'),
            {"i": user_id, "e": f"{user_id}@example.com"},
        )
        c.execute(
            text(
                "INSERT INTO outbox (id, user_id, event_type, payload, trace_context,"
                " occurred_at, available_at) VALUES (gen_random_uuid(), :u, 'unit.saved.v1',"
                " '{}', '{}', now(), now())"
            ),
            {"u": user_id},
        )
    try:
        with pytest.raises(RuntimeError, match="0027 downgrade"):
            command.downgrade(alembic_cfg, "0026")
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM outbox WHERE user_id = :u"), {"u": user_id})
            c.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": user_id})
        command.upgrade(alembic_cfg, "head")
