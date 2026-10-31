"""T7.M2, migration 0025 (ADR-0008, additions only; ARCH §6.2; no user story, so no AC): the
round trip puts the shape back, the downgrade removes the new tables or refuses, never
deleting data."""

import uuid
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

NEW_TABLES = ("practice_state", "practice_log", "command_log", "unit_edge")
NEW_QUESTION_COLUMNS = {"bank_document_id", "bank_ord"}
RUN = uuid.uuid4()
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def tables(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


def question_columns(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'question'"
                )
            ).scalars()
        )


def test_single_alembic_head(alembic_cfg: Config) -> None:
    # Red when: two migrations branch from the same parent.
    heads = ScriptDirectory.from_config(alembic_cfg).get_heads()
    assert heads == ["0026"]


def test_0025_round_trip(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: a table, column or constraint is left behind or missing after 0024->0025->0024
    # ->0025, or the models differ from the database.
    try:
        command.downgrade(alembic_cfg, "0024")
        assert not set(NEW_TABLES) & tables(engine)
        assert not NEW_QUESTION_COLUMNS & question_columns(engine)
        with engine.connect() as connection:
            definition = connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conname = 'ck_question_type_ref_origin_known'"
                )
            ).scalar_one()
        assert "'default'" not in definition
    finally:
        command.upgrade(alembic_cfg, "head")
    assert set(NEW_TABLES) <= tables(engine)
    assert NEW_QUESTION_COLUMNS <= question_columns(engine)


def test_models_match_the_migrated_database(engine: Engine) -> None:
    # Red when: a model of group 2 differs from what 0025 built (type, nullability, index).
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from core_api.db.base import Base
    from core_api.db.models import __all__ as _  # noqa: F401

    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diff = [
            item
            for item in compare_metadata(context, Base.metadata)
            if any(name in repr(item) for name in (*NEW_TABLES, "bank_", "ref_origin"))
        ]
    assert diff == []


def seed_user(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    user, subject = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text('INSERT INTO "user" (id, email) VALUES (:id, :e)'),
            {"id": user, "e": f"{user}@example.com"},
        )
        connection.execute(
            text("INSERT INTO subject (id, user_id, name) VALUES (:id, :u, 'Mạng')"),
            {"id": subject, "u": user},
        )
    return user, subject


def seed_unit(engine: Engine, user: uuid.UUID, subject: uuid.UUID) -> uuid.UUID:
    unit = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO knowledge_unit (id, user_id, subject_id, title, summary, kind,"
                " status, run_id) VALUES (:id, :u, :s, 't', 's', 'concept', 'active', :r)"
            ),
            {"id": unit, "u": user, "s": subject, "r": RUN},
        )
    return unit


def seed_question(engine: Engine, user: uuid.UUID, subject: uuid.UUID) -> uuid.UUID:
    question = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO question (id, user_id, subject_id, level, prompt, reference_answer,"
                " status, content_hash, run_id) VALUES (:id, :u, :s, 1, 'p', 'a', 'active', :h, :r)"
            ),
            {"id": question, "u": user, "s": subject, "h": "0" * 64, "r": RUN},
        )
    return question


def fill_practice_state(engine: Engine, user: uuid.UUID, subject: uuid.UUID) -> None:
    question = seed_question(engine, user, subject)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO practice_state (id, user_id, question_id, phase, stability, difficulty,"  # noqa: E501
                " due, last_review) VALUES (gen_random_uuid(), :u, :q, 'review', 1, 5, now(), now())"  # noqa: E501
            ),
            {"u": user, "q": question},
        )


def fill_practice_log(engine: Engine, user: uuid.UUID, subject: uuid.UUID) -> None:
    question = seed_question(engine, user, subject)
    review, attempt, grade = (uuid.uuid4() for _ in range(3))
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO review_session (id, user_id, learning_day, started_at)"
                " VALUES (:r, :u, '2026-10-30', now())"
            ),
            {"r": review, "u": user},
        )
        connection.execute(
            text(
                "INSERT INTO attempt (id, user_id, review_session_id, question_id, status,"
                " submitted_at) VALUES (:a, :u, :r, :q, 'submitted', now())"
            ),
            {"a": attempt, "u": user, "r": review, "q": question},
        )
        connection.execute(
            text(
                "INSERT INTO grade (id, user_id, attempt_id, source, overall)"
                " VALUES (:g, :u, :a, 'ai', 'correct')"
            ),
            {"g": grade, "u": user, "a": attempt},
        )
        connection.execute(
            text(
                "INSERT INTO practice_log (id, user_id, question_id, rating, reviewed_at, grade_id)"
                " VALUES (gen_random_uuid(), :u, :q, 3, now(), :g)"
            ),
            {"u": user, "q": question, "g": grade},
        )


def fill_command_log(engine: Engine, user: uuid.UUID, subject: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO command_log (id, user_id, subject_id, raw_text, ops_json, inverse_json,"  # noqa: E501
                " status, affected_count) VALUES (gen_random_uuid(), :u, :s, 'x', '[]', '[]', 'applied', 0)"  # noqa: E501
            ),
            {"u": user, "s": subject},
        )


def fill_unit_edge(engine: Engine, user: uuid.UUID, subject: uuid.UUID) -> None:
    a, b = seed_unit(engine, user, subject), seed_unit(engine, user, subject)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO unit_edge (id, user_id, subject_id, src_unit_id, dst_unit_id, kind,"
                " origin, status) VALUES (gen_random_uuid(), :u, :s, :a, :b, 'part_of', 'user', 'active')"  # noqa: E501
            ),
            {"u": user, "s": subject, "a": a, "b": b},
        )


FILLERS = {
    "practice_state": fill_practice_state,
    "practice_log": fill_practice_log,
    "command_log": fill_command_log,
    "unit_edge": fill_unit_edge,
}


GUARDED = ("practice_log", "attempt", "grade", "review_session")


def erase_user(engine: Engine, user: uuid.UUID) -> None:
    """Remove a test user whose history the append-only triggers protect: they are switched off
    for this clean-up only."""
    with engine.begin() as connection:
        for table in GUARDED:
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))  # noqa: S608
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": user})
        for table in GUARDED:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))  # noqa: S608


@pytest.mark.parametrize("table", NEW_TABLES)
def test_0025_downgrade_refuses_when_any_new_table_has_rows(
    engine: Engine, alembic_cfg: Config, table: str
) -> None:
    # Red when: the downgrade drops a table that still holds learner data, or checks only some.
    user, subject = seed_user(engine)
    FILLERS[table](engine, user, subject)
    try:
        with pytest.raises(RuntimeError, match="0025 downgrade"):
            command.downgrade(alembic_cfg, "0024")
        assert table in tables(engine)
        with engine.connect() as connection:
            held = connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE user_id = :u"),  # noqa: S608
                {"u": user},
            ).scalar_one()
        assert held == 1
    finally:
        command.upgrade(alembic_cfg, "head")
        erase_user(engine, user)


@pytest.mark.parametrize("held", ["default origin", "bank link"])
def test_0025_downgrade_refuses_default_origin_and_bank_link(
    engine: Engine, alembic_cfg: Config, held: str
) -> None:
    # Red when: the downgrade narrows the CHECK over a 'default' row or drops a bank link.
    user, subject = seed_user(engine)
    with engine.begin() as connection:
        if held == "default origin":
            connection.execute(
                text(
                    "INSERT INTO question_type (id, user_id, subject_id, name, ref_time_s, ref_origin)"  # noqa: E501
                    " VALUES (gen_random_uuid(), :u, :s, 'Giải thích', 60, 'default')"
                ),
                {"u": user, "s": subject},
            )
        else:
            document = uuid.uuid4()
            sha = "ab" * 32
            connection.execute(
                text(
                    "INSERT INTO document (id, user_id, subject_id, short_name, sha256,"
                    " size_bytes, object_key, status, presigned_at, uploaded_at, role)"
                    " VALUES (:d, :u, :s, 'x', :sha, 1, :k, 'uploaded', now(), now(),"
                    " 'question_bank')"
                ),
                {
                    "d": document,
                    "u": user,
                    "s": subject,
                    "sha": sha,
                    "k": f"users/{user}/subjects/{subject}/raw/{sha}.pdf",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO question (id, user_id, subject_id, level, prompt, reference_answer,"  # noqa: E501
                    " status, content_hash, run_id, bank_document_id, bank_ord)"
                    " VALUES (gen_random_uuid(), :u, :s, 1, 'p', 'a', 'active', :h, :r, :d, 0)"
                ),
                {"u": user, "s": subject, "h": "1" * 64, "r": RUN, "d": document},
            )
    try:
        with pytest.raises(RuntimeError, match="0025 downgrade"):
            command.downgrade(alembic_cfg, "0024")
        assert NEW_QUESTION_COLUMNS <= question_columns(engine)
    finally:
        command.upgrade(alembic_cfg, "head")
        erase_user(engine, user)


def test_0025_downgrade_refuses_when_a_section_has_studied_weight(
    engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: the downgrade drops studied_weight over learner progress.
    user, subject = seed_user(engine)
    document, sha = uuid.uuid4(), "ab" * 32
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO document (id, user_id, subject_id, short_name, sha256, size_bytes,"
                " object_key, status, presigned_at, uploaded_at)"
                " VALUES (:d, :u, :s, 'x', :sha, 1, :k, 'uploaded', now(), now())"
            ),
            {
                "d": document,
                "u": user,
                "s": subject,
                "sha": sha,
                "k": f"users/{user}/subjects/{subject}/raw/{sha}.pdf",
            },
        )
        connection.execute(
            text(
                "INSERT INTO doc_section (id, user_id, subject_id, document_id, ord, title,"
                " unit, source, studied_weight)"
                " VALUES (gen_random_uuid(), :u, :s, :d, 0, 'C1', 'page', 'user', 2)"
            ),
            {"u": user, "s": subject, "d": document},
        )
    try:
        with pytest.raises(RuntimeError, match="0025 downgrade"):
            command.downgrade(alembic_cfg, "0024")
    finally:
        command.upgrade(alembic_cfg, "head")
        erase_user(engine, user)
