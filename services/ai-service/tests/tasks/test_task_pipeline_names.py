"""T4.16b: the tasks `chunk_units` and `generate_questions` are known to the audit tables."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from ai_service.config import Settings
from ai_service.db.models import TASKS as DB_TASKS
from ai_service.llm.types import TASKS as LLM_TASKS

NEW_TASKS = ("chunk_units", "generate_questions")


def _insert_run(engine: Engine, task: str) -> None:
    with engine.connect() as connection, connection.begin() as transaction:
        connection.execute(
            text(
                "INSERT INTO pipeline_run (id, user_id, subject_id, task, prompt_version,"
                " prompt_sha256) VALUES (:id, :u, :s, :t, 'v1', :h)"
            ),
            {"id": uuid.uuid4(), "u": uuid.uuid4(), "s": uuid.uuid4(), "t": task, "h": "0" * 64},
        )
        transaction.rollback()


@pytest.mark.parametrize("task", NEW_TASKS)
def test_t416b_pipeline_run_accepts_the_task(engine: Engine, task: str) -> None:
    # Red when: the migration did not relax ck_pipeline_run_task_known.
    _insert_run(engine, task)


@pytest.mark.parametrize("task", NEW_TASKS)
def test_t416b_llm_call_check_names_the_task(engine: Engine, task: str) -> None:
    with engine.connect() as connection:
        definition = connection.scalar(
            text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n"),
            {"n": "ck_llm_call_task_known"},
        )
    assert definition is not None
    assert task in definition


def test_t416b_still_refuses_an_unknown_task(engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        _insert_run(engine, "bogus")


def test_t416b_python_task_lists_agree() -> None:
    assert set(LLM_TASKS) == DB_TASKS
    assert set(NEW_TASKS) <= DB_TASKS


def test_t416b_default_models_cover_the_new_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert set(settings.llm_models) == set(LLM_TASKS)
