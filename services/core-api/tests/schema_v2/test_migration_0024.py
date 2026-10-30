"""T7.6, migration 0024 (ADR-0008, additions only): old rows survive the upgrade, the downgrade
puts the old shape back or refuses, never deleting data."""

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def seed_note(engine: Engine, mime: str, ext: str) -> uuid.UUID:
    user, subject, session = (uuid.uuid4() for _ in range(3))
    sha = "ab" * 32
    with engine.begin() as connection:
        connection.execute(
            text('INSERT INTO "user" (id, email) VALUES (:id, :e)'),
            {"id": user, "e": f"{user}@example.com"},
        )
        connection.execute(
            text("INSERT INTO subject (id, user_id, name) VALUES (:id, :u, 'Mạng')"),
            {"id": subject, "u": user},
        )
        connection.execute(
            text(
                "INSERT INTO study_session (id, user_id, subject_id, description_raw, status,"
                " extraction) VALUES (:id, :u, :s, 'd', 'draft', 'proposed')"
            ),
            {"id": session, "u": user, "s": subject},
        )
        connection.execute(
            text(
                "INSERT INTO note_file (id, user_id, session_id, object_key, sha256, mime,"
                " size_bytes) VALUES (gen_random_uuid(), :u, :ss, :k, :sha, :m, 1)"
            ),
            {
                "u": user,
                "ss": session,
                "sha": sha,
                "m": mime,
                "k": f"users/{user}/sessions/{session}/notes/{sha}.{ext}",
            },
        )
    return user


def delete_user(engine: Engine, user: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": user})


def test_0024_up_down_keeps_data(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: the downgrade or the re-upgrade loses or breaks an old note row (P1).
    command.downgrade(alembic_cfg, "0023")
    user = seed_note(engine, "application/pdf", "pdf")
    try:
        command.upgrade(alembic_cfg, "head")
        with engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM note_file WHERE user_id = :u"), {"u": user}
            ).scalar_one()
        assert count == 1
    finally:
        command.upgrade(alembic_cfg, "head")
        delete_user(engine, user)


def test_downgrade_refuses_while_a_docx_note_exists(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: the downgrade deletes the row or narrows the CHECK over it.
    user = seed_note(engine, DOCX, "docx")
    try:
        with pytest.raises(RuntimeError, match="0024 downgrade"):
            command.downgrade(alembic_cfg, "0023")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM note_file WHERE user_id = :u"), {"u": user}
                ).scalar_one()
                == 1
            )
    finally:
        command.upgrade(alembic_cfg, "head")
        delete_user(engine, user)


def test_downgrade_drops_page_columns_and_upgrade_restores_them(
    engine: Engine, alembic_cfg: Config
) -> None:
    def columns() -> set[str]:
        with engine.connect() as connection:
            return set(
                connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns"
                        " WHERE table_name = 'doc_section'"
                    )
                ).scalars()
            )

    try:
        command.downgrade(alembic_cfg, "0023")
        assert not {"first_page", "last_page"} & columns()
    finally:
        command.upgrade(alembic_cfg, "head")
    assert {"first_page", "last_page"} <= columns()
