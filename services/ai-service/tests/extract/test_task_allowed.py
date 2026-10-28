"""T4.10: the task `extract_session` is known to the audit tables and the task-model table."""

import json
import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from ai_service.config import Settings
from ai_service.db.models import TASKS as DB_TASKS
from ai_service.llm.types import TASKS as LLM_TASKS

FAKE_KEY = "sk-ant-test"


def _insert_run(engine: Engine, task: str) -> None:
    # Rolled back: a row left behind would stop the downgrade test (the old CHECK refuses it).
    with engine.connect() as connection, connection.begin() as transaction:
        connection.execute(
            text(
                "INSERT INTO pipeline_run (id, user_id, subject_id, task, prompt_version,"
                " prompt_sha256) VALUES (:id, :u, :s, :t, 'v1', :h)"
            ),
            {"id": uuid.uuid4(), "u": uuid.uuid4(), "s": uuid.uuid4(), "t": task, "h": "0" * 64},
        )
        transaction.rollback()


def test_t410_pipeline_run_accepts_extract_session(engine: Engine) -> None:
    # Red when: the migration did not relax ck_pipeline_run_task_known.
    _insert_run(engine, "extract_session")


def test_t410_pipeline_run_still_refuses_an_unknown_task(engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        _insert_run(engine, "bogus")


def test_t410_llm_call_check_names_extract_session(engine: Engine) -> None:
    with engine.connect() as connection:
        definition = connection.scalar(
            text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n"),
            {"n": "ck_llm_call_task_known"},
        )
    assert definition is not None
    assert "extract_session" in definition


def test_t410_python_task_lists_agree() -> None:
    assert set(LLM_TASKS) == DB_TASKS


def test_t410_default_models_cover_every_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert set(settings.llm_models) == set(LLM_TASKS)


def test_t410_a_task_table_without_extract_session_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_LLM_MODELS", json.dumps({"grade": "claude-haiku-5-5"}))
    with pytest.raises(ValueError, match="llm_models"):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
