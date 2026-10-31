"""T7.M3, ai migration 0009 (tester): the downgrade puts back exactly the task list of 0008.
test_database.py covers the upgrade (new tasks accepted) and the full base round trip; neither
looks at the database while it sits on 0008, so a downgrade that keeps a new task or loses an
old one would pass both."""

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

TASKS_0008 = [
    "grade",
    "extract_session",
    "chunk_units",
    "generate_questions",
    "parse_command",
    "syllabus_toc",
    "draft_units",
    "read_notes",
]
TASKS_0009 = ["grade_practice", "draft_answer", "parse_question_bank"]
INSERT_RUN = (
    "INSERT INTO pipeline_run (id, user_id, subject_id, task, prompt_version, prompt_sha256)"
    " VALUES (:id, :u, :s, :t, 'v1', :sha)"
)


def run_values(task: str) -> dict[str, object]:
    return {"id": uuid.uuid4(), "u": uuid.uuid4(), "s": uuid.uuid4(), "t": task, "sha": "0" * 64}


def drop_new_task_rows(engine: Engine) -> None:
    in_new = ", ".join(f"'{t}'" for t in TASKS_0009)
    with engine.begin() as connection:
        connection.execute(text(f"DELETE FROM llm_call WHERE task IN ({in_new})"))  # noqa: S608
        connection.execute(text(f"DELETE FROM pipeline_run WHERE task IN ({in_new})"))  # noqa: S608


def task_check_accepts(engine: Engine, table: str, task: str) -> bool:
    """Whether the task CHECK of `table` lets `task` in (asked of Postgres, nothing written)."""
    with engine.connect() as connection:
        definition = connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conrelid = CAST(:t AS regclass) AND conname = :n"
            ),
            {"t": table, "n": f"ck_{table}_task_known"},
        ).scalar_one()
    return f"'{task}'" in definition


def test_t7m3_downgrade_to_0008_restores_the_0008_task_list(
    engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: 0009's downgrade keeps a new task allowed, or drops one 0008 allowed.
    drop_new_task_rows(engine)
    try:
        command.downgrade(alembic_cfg, "0008")
        for table in ("pipeline_run", "llm_call"):
            assert [t for t in TASKS_0009 if task_check_accepts(engine, table, t)] == []
            assert [t for t in TASKS_0008 if not task_check_accepts(engine, table, t)] == []
        with engine.connect() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(text(INSERT_RUN), run_values("grade_practice"))
            connection.rollback()
    finally:
        command.upgrade(alembic_cfg, "head")
    for table in ("pipeline_run", "llm_call"):
        assert all(task_check_accepts(engine, table, t) for t in TASKS_0008 + TASKS_0009)


def test_t7m3_downgrade_refuses_while_a_new_task_row_exists(
    engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: the downgrade drops or hides a row with a new task instead of refusing.
    values = run_values("parse_question_bank")
    with engine.begin() as connection:
        head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        connection.execute(text(INSERT_RUN), values)
    try:
        with pytest.raises(DBAPIError):
            command.downgrade(alembic_cfg, "0008")
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            kept = connection.execute(
                text("SELECT count(*) FROM pipeline_run WHERE id = :id"), {"id": values["id"]}
            ).scalar()
        assert (version, kept) == (head, 1)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM pipeline_run WHERE id = :id"), {"id": values["id"]}
            )
        command.upgrade(alembic_cfg, "head")
