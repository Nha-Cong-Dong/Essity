"""T7.M3, migration 0026 (ADR-0008, additions only; ARCH §6.2; PLAN T8.4): attempt timing columns.
The round trip puts the shape back; the checks refuse impossible timing; the attempt guard
(ADR-0024) still lets a draft become submitted with its timing, and freezes it afterwards."""

import uuid
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

Seeded = tuple[uuid.UUID, uuid.UUID, uuid.UUID]
TIMING = {"served_at", "hidden_ms", "active_ms", "timing_ok"}


def attempt_columns(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'attempt'"
                )
            ).scalars()
        )


def test_single_alembic_head(alembic_cfg: Config) -> None:
    # Red when: two migrations branch from the same parent, or 0026 is not the head.
    assert ScriptDirectory.from_config(alembic_cfg).get_heads() == ["0026"]


def test_0026_round_trip(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: a column or check is left behind or missing after 0025->0026, or models differ.
    try:
        command.downgrade(alembic_cfg, "0025")
        assert not TIMING & attempt_columns(engine)
    finally:
        command.upgrade(alembic_cfg, "head")
    assert TIMING <= attempt_columns(engine)


def test_models_match_the_migrated_database(engine: Engine) -> None:
    # Red when: the Attempt model differs from what 0026 built (type, nullability, check).
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from core_api.db.base import Base
    from core_api.db.models import __all__ as _  # noqa: F401

    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diff = [
            item
            for item in compare_metadata(context, Base.metadata)
            if "procrastinate" not in repr(item) and "attempt" in repr(item)
        ]
    assert diff == []


def test_model_checks_match_the_database(engine: Engine) -> None:
    # Red when: an Attempt CHECK differs by name from what 0026 built (compare_metadata skips them).
    from core_api.db.base import Base
    from core_api.db.models import __all__ as _  # noqa: F401

    names = [str(getattr(c, "name", None)) for c in Base.metadata.tables["attempt"].constraints]
    wanted = {n for n in names if n.startswith("ck_attempt_")}
    with engine.connect() as connection:
        built = set(
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conrelid = 'attempt'::regclass"
                    " AND contype = 'c'"
                )
            ).scalars()
        )
    assert wanted == {n for n in built if n.startswith("ck_attempt_")}


# Rows go through db_session: it rolls back, because attempt rows can never be deleted afterwards.
@pytest.fixture
def seeded(db_session: Session) -> Seeded:
    user, subject, question, review = (uuid.uuid4() for _ in range(4))
    for sql, values in (
        ('INSERT INTO "user" (id, email) VALUES (:id, :e)', {"id": user, "e": f"{user}@x.org"}),
        (
            "INSERT INTO subject (id, user_id, name) VALUES (:id, :u, 'Mạng')",
            {"id": subject, "u": user},
        ),
        (
            "INSERT INTO question (id, user_id, subject_id, level, prompt, reference_answer,"
            " status, content_hash, run_id) VALUES (:id, :u, :s, 1, 'p', 'a', 'active', :h, :r)",
            {"id": question, "u": user, "s": subject, "h": "0" * 64, "r": uuid.uuid4()},
        ),
        (
            "INSERT INTO review_session (id, user_id, learning_day, started_at)"
            " VALUES (:r, :u, '2026-11-01', now())",
            {"r": review, "u": user},
        ),
    ):
        db_session.execute(text(sql), values)
    return user, question, review


def insert_attempt(
    db_session: Session, seeded: Seeded, status: str = "draft", **timing: Any
) -> uuid.UUID:
    user, question, review = seeded
    cols = ["id", "user_id", "review_session_id", "question_id", "status", *timing]
    submitted = ", submitted_at" if status == "submitted" else ""
    values = ", now()" if status == "submitted" else ""
    attempt = uuid.uuid4()
    db_session.execute(
        text(
            f"INSERT INTO attempt ({', '.join(cols)}{submitted})"  # noqa: S608
            f" VALUES ({', '.join(':' + k for k in cols)}{values})"
        ),
        {
            "id": attempt,
            "user_id": user,
            "review_session_id": review,
            "question_id": question,
            "status": status,
            **timing,
        },
    )
    return attempt


def test_attempt_without_timing_still_inserts(db_session: Session, seeded: Seeded) -> None:
    # Red when: a timing column is NOT NULL (old review attempts have no timing).
    insert_attempt(db_session, seeded)


def test_full_timing_on_a_submitted_attempt_is_accepted(
    db_session: Session, seeded: Seeded
) -> None:
    insert_attempt(
        db_session,
        seeded,
        "submitted",
        served_at="2026-11-01T09:00:00Z",
        hidden_ms=0,
        active_ms=1500,
        timing_ok=True,
    )


SERVED = "2026-11-01T09:00:00Z"


@pytest.mark.parametrize(
    "timing",
    [
        {"served_at": SERVED, "hidden_ms": -1, "active_ms": 5, "timing_ok": True},
        {"served_at": SERVED, "hidden_ms": 0, "active_ms": -1, "timing_ok": True},
        {"hidden_ms": 0, "active_ms": 5, "timing_ok": True},  # active needs served_at
        {"served_at": SERVED, "active_ms": 5, "timing_ok": True},  # active needs hidden_ms
        {"served_at": SERVED, "hidden_ms": 0, "timing_ok": True},  # timing_ok without active_ms
        {"served_at": SERVED, "hidden_ms": 0, "active_ms": 5},  # active_ms without timing_ok
    ],
)
def test_impossible_timing_is_refused(
    db_session: Session, seeded: Seeded, timing: dict[str, Any]
) -> None:
    # Red when: a CHECK (non-negative, all-or-none, active needs hidden and served_at) is missing.
    with pytest.raises(IntegrityError), db_session.begin_nested():
        insert_attempt(db_session, seeded, "submitted", **timing)


def test_measured_timing_needs_a_submitted_attempt(db_session: Session, seeded: Seeded) -> None:
    # Red when: a draft can carry an answer time (the time exists once the answer is in).
    with pytest.raises(IntegrityError), db_session.begin_nested():
        insert_attempt(
            db_session,
            seeded,
            "draft",
            served_at=SERVED,
            hidden_ms=0,
            active_ms=5,
            timing_ok=True,
        )


def test_timing_is_written_with_the_submit_then_frozen(db_session: Session, seeded: Seeded) -> None:
    # Red when: attempt_guard blocks the submit UPDATE, or lets timing change afterwards.
    attempt = insert_attempt(db_session, seeded, served_at=SERVED)
    db_session.execute(
        text(
            "UPDATE attempt SET status = 'submitted', submitted_at = now(), hidden_ms = 0,"
            " active_ms = 900, timing_ok = true WHERE id = :a"
        ),
        {"a": attempt},
    )
    for change in ("active_ms = 1", "served_at = now()"):
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.execute(text(f"UPDATE attempt SET {change} WHERE id = :a"), {"a": attempt})  # noqa: S608
