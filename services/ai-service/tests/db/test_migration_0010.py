"""T9.6b, ai migration 0010: the downgrade puts back the task list of 0009 and refuses while a
row has one of the new tasks."""

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

NEW = ("generate_like", "judge_questions")
INSERT_RUN = (
    "INSERT INTO pipeline_run (id, user_id, subject_id, task, prompt_version, prompt_sha256)"
    " VALUES (:id, :u, :s, 'generate_like', 'v1', :sha)"
)


def accepts(engine: Engine, table: str, task: str) -> bool:
    with engine.connect() as connection:
        definition = connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conrelid = CAST(:t AS regclass) AND conname = :n"
            ),
            {"t": table, "n": f"ck_{table}_task_known"},
        ).scalar_one()
    return f"'{task}'" in definition


def test_downgrade_to_0009_drops_only_the_new_tasks(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: 0010's downgrade keeps a new task allowed or drops an older one.
    command.downgrade(alembic_cfg, "0009")
    try:
        for table in ("pipeline_run", "llm_call"):
            assert [t for t in NEW if accepts(engine, table, t)] == []
            assert accepts(engine, table, "draft_answer")
    finally:
        command.upgrade(alembic_cfg, "head")
    assert all(accepts(engine, t, task) for t in ("pipeline_run", "llm_call") for task in NEW)


def test_downgrade_refuses_while_a_new_task_row_exists(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: the downgrade drops or hides a row with a new task instead of refusing.
    values = {"id": uuid.uuid4(), "u": uuid.uuid4(), "s": uuid.uuid4(), "sha": "0" * 64}
    with engine.begin() as connection:
        connection.execute(text(INSERT_RUN), values)
    try:
        with pytest.raises(DBAPIError):
            command.downgrade(alembic_cfg, "0009")
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM pipeline_run WHERE id = :id"), {"id": values["id"]}
            )
        command.upgrade(alembic_cfg, "head")
