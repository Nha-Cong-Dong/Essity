"""T7.1, migration 0023 (ADR-0008, additions only; spec v2 §16.2; no user story, so no AC):
old rows read as the spec says after the upgrade, and the downgrade puts the old shape back
(or refuses, never deleting data)."""

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

RUN = uuid.uuid4()
NEW_TABLES = (
    "doc_section",
    "unit_revision",
    "unit_section",
    "question_type",
    "question_section",
    "submission",
)


def tables(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


def seed_old_rows(engine: Engine, unit_status: str = "active") -> uuid.UUID:
    """One user with an old-shape document, unit and question; returns the user id."""
    user, subject, document, unit, question = (uuid.uuid4() for _ in range(5))
    sha = "ab" * 32
    key = f"users/{user}/subjects/{subject}/raw/{sha}.pdf"
    with engine.begin() as connection:
        connection.execute(
            text('INSERT INTO "user" (id, email) VALUES (:id, :email)'),
            {"id": user, "email": f"{user}@example.com"},
        )
        connection.execute(
            text("INSERT INTO subject (id, user_id, name) VALUES (:id, :u, 'Mạng')"),
            {"id": subject, "u": user},
        )
        connection.execute(
            text(
                "INSERT INTO document (id, user_id, subject_id, short_name, sha256, size_bytes,"
                " object_key, status, presigned_at, uploaded_at)"
                " VALUES (:id, :u, :s, 'x', :sha, 1, :key, 'uploaded', now(), now())"
            ),
            {"id": document, "u": user, "s": subject, "sha": sha, "key": key},
        )
        connection.execute(
            text(
                "INSERT INTO knowledge_unit (id, user_id, subject_id, title, summary, kind,"
                " status, run_id) VALUES (:id, :u, :s, 't', 's', 'concept', :us, :run)"
            ),
            {"id": unit, "u": user, "s": subject, "run": RUN, "us": unit_status},
        )
        connection.execute(
            text(
                "INSERT INTO question (id, user_id, subject_id, level, prompt, reference_answer,"
                " status, content_hash, run_id)"
                " VALUES (:id, :u, :s, 1, 'p', 'a', 'active', :h, :run)"
            ),
            {"id": question, "u": user, "s": subject, "h": "0" * 64, "run": RUN},
        )
    return user


def delete_user(engine: Engine, user: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": user})


def test_upgrade_gives_old_rows_the_v2_values(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: a backfill is missing, or the old rows break a new constraint on upgrade.
    command.downgrade(alembic_cfg, "0022")
    user = seed_old_rows(engine)
    try:
        command.upgrade(alembic_cfg, "head")
        with engine.connect() as connection:
            document = connection.execute(
                text("SELECT role, format FROM document WHERE user_id = :u"), {"u": user}
            ).one()
            unit = connection.execute(
                text("SELECT status, version FROM knowledge_unit WHERE user_id = :u"), {"u": user}
            ).one()
            question = connection.execute(
                text(
                    "SELECT source, quality_status, type_id, answer_origin FROM question"
                    " WHERE user_id = :u"
                ),
                {"u": user},
            ).one()
        assert tuple(document) == ("auxiliary", "pdf")
        # Old 'active' rows became canonical in 0031 (T7.11).
        assert tuple(unit) == ("canonical", 1)
        assert tuple(question) == ("review_auto", "ok", None, None)
    finally:
        command.upgrade(alembic_cfg, "head")
        delete_user(engine, user)


def test_downgrade_removes_the_new_tables_and_upgrade_brings_them_back(
    engine: Engine, alembic_cfg: Config
) -> None:
    try:
        command.downgrade(alembic_cfg, "0022")
        assert not set(NEW_TABLES) & tables(engine)
        with engine.connect() as connection:
            columns = set(
                connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns"
                        " WHERE table_name = 'question'"
                    )
                ).scalars()
            )
        assert "level" in columns
        assert not {"source", "type_id", "quality_status", "answer_text"} & columns
    finally:
        command.upgrade(alembic_cfg, "head")
    assert set(NEW_TABLES) <= tables(engine)


def test_downgrade_makes_run_id_required_again(engine: Engine, alembic_cfg: Config) -> None:
    # Red when (tester): the downgrade leaves question.run_id nullable, so 0022 code reading
    # `run_id` as always set meets NULLs written after a later re-upgrade.
    try:
        command.downgrade(alembic_cfg, "0022")
        with engine.connect() as connection:
            nullable = connection.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns"
                    " WHERE table_name = 'question' AND column_name = 'run_id'"
                )
            ).scalar_one()
        assert nullable == "NO"
    finally:
        command.upgrade(alembic_cfg, "head")


def test_downgrade_restores_the_old_status_check(engine: Engine, alembic_cfg: Config) -> None:
    try:
        command.downgrade(alembic_cfg, "0022")
        with engine.connect() as connection:
            definition = connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conname = 'ck_knowledge_unit_status_known'"
                )
            ).scalar_one()
        assert "canonical" not in definition and "draft" not in definition
    finally:
        command.upgrade(alembic_cfg, "head")


@pytest.mark.parametrize("kind", ["draft unit", "canonical unit", "question without run"])
def test_downgrade_refuses_when_it_would_lose_data(
    engine: Engine, alembic_cfg: Config, kind: str
) -> None:
    # Red when: the downgrade deletes rows or turns drafts into 'active' to get its way (F5).
    match = "without a run_id" if kind.startswith("question") else "units with status"
    user = seed_old_rows(engine, "canonical")
    with engine.begin() as connection:
        if kind.endswith("unit"):
            # Red when (canonical, tester): the guard checks only one of the two new statuses.
            connection.execute(
                text("UPDATE knowledge_unit SET status = :st WHERE user_id = :u"),
                {"u": user, "st": kind.split()[0]},
            )
        else:
            # The unit guard fires first, so the unit must not be canonical or draft here.
            connection.execute(
                text("UPDATE knowledge_unit SET status = 'retired' WHERE user_id = :u"),
                {"u": user},
            )
            connection.execute(
                text("UPDATE question SET source = 'bank', run_id = NULL WHERE user_id = :u"),
                {"u": user},
            )
    try:
        with pytest.raises(RuntimeError, match=match):
            command.downgrade(alembic_cfg, "0022")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM question WHERE user_id = :u"), {"u": user}
                ).scalar_one()
                == 1
            )
    finally:
        command.upgrade(alembic_cfg, "head")
        delete_user(engine, user)
