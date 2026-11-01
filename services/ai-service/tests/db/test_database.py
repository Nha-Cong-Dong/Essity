"""T2.10: database `ai` (pipeline_run, llm_call). Runs on the real test PostgreSQL (conftest)."""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_service.db.base import NAMING_CONVENTION, Base
from ai_service.db.models import LlmCall, PipelineRun

TABLES = {"pipeline_run", "llm_call", "processed_event"}
T83_TASKS = ["grade_practice", "draft_answer", "parse_question_bank"]
T96_TASKS = ["generate_like", "judge_questions"]
T83_TASKS_SQL = ", ".join(f"'{task}'" for task in [*T83_TASKS, *T96_TASKS])


def table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def test_t210_migrations_go_down_to_base_and_back_up(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: a migration's downgrade leaves a table behind or its upgrade cannot run twice.
    with engine.begin() as connection:  # 0007's downgrade refuses while a row has the new task
        connection.execute(text("DELETE FROM llm_call WHERE task = 'syllabus_toc'"))
        connection.execute(text("DELETE FROM pipeline_run WHERE task = 'syllabus_toc'"))
        connection.execute(text("DELETE FROM llm_call WHERE task IN ('draft_units','read_notes')"))
        connection.execute(
            text("DELETE FROM pipeline_run WHERE task IN ('draft_units','read_notes')")
        )
        connection.execute(text(f"DELETE FROM llm_call WHERE task IN ({T83_TASKS_SQL})"))
        connection.execute(text(f"DELETE FROM pipeline_run WHERE task IN ({T83_TASKS_SQL})"))
    command.downgrade(alembic_cfg, "base")
    assert not TABLES & table_names(engine)
    command.upgrade(alembic_cfg, "head")
    assert TABLES <= table_names(engine)


def test_t210_models_and_migrations_match(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: a model changes without a migration (`alembic check`, as CI runs it).
    try:
        command.check(alembic_cfg)
    except CommandError as exc:  # pragma: no cover - the message is the useful part
        pytest.fail(f"models and migrations differ: {exc}")


def test_t210_constraint_names_follow_the_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def new_run(**overrides: Any) -> PipelineRun:
    values: dict[str, Any] = {
        "user_id": uuid.uuid4(),
        "subject_id": uuid.uuid4(),
        "task": "grade",
        "prompt_version": "v1",
        "prompt_sha256": "0" * 64,
    }
    return PipelineRun(**{**values, **overrides})


def new_call(run: PipelineRun, **overrides: Any) -> LlmCall:
    values: dict[str, Any] = {
        "pipeline_run_id": run.id,
        "user_id": run.user_id,
        "subject_id": run.subject_id,
        "task": "grade",
        "provider": "fake",
        "model": "fake-grader-v1",
        "prompt_version": "v1",
        "attempt": 1,
        "input": {"messages": []},
        "cost_usd": Decimal(0),
        "latency_ms": 0,
    }
    return LlmCall(**{**values, **overrides})


def test_t210_llm_call_keeps_cost_as_an_exact_decimal(engine: Engine) -> None:
    # Red when: cost is a float column, and summing many small calls drifts (T2.11 quotas).
    with Session(engine) as session:
        run = new_run()
        session.add(run)
        session.flush()
        call = new_call(run, cost_usd=Decimal("0.000123"), input_tokens=10, output_tokens=2)
        session.add(call)
        session.flush()
        session.expire_all()
        assert session.get(LlmCall, call.id).cost_usd == Decimal("0.000123")  # pyright: ignore[reportOptionalMemberAccess]
        session.rollback()


@pytest.mark.parametrize("missing", ["user_id", "subject_id"])
def test_t210_llm_call_without_user_or_subject_is_refused(engine: Engine, missing: str) -> None:
    # Red when: llm_call.user_id is nullable, and a call nobody owns escapes quotas and audits.
    with Session(engine) as session:
        run = new_run()
        session.add(run)
        session.flush()
        session.add(new_call(run, **{missing: None}))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


@pytest.mark.parametrize("missing", ["user_id", "subject_id"])
def test_b4_pipeline_run_without_user_or_subject_is_refused(engine: Engine, missing: str) -> None:
    # Red when: pipeline_run.user_id/subject_id are nullable (B4: tightening later is harder).
    with Session(engine) as session:
        session.add(new_run(**{missing: None}))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


@pytest.mark.parametrize(
    ("column", "value"),
    [("provider", "openai"), ("attempt", 0), ("cost_usd", Decimal("-1")), ("input_tokens", -1)],
)
def test_t210_llm_call_checks_its_values(engine: Engine, column: str, value: object) -> None:
    with Session(engine) as session:
        run = new_run()
        session.add(run)
        session.flush()
        session.add(new_call(run, **{column: value}))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_t210_query_creates_a_span(engine: Engine, spans: InMemorySpanExporter) -> None:
    # Red when: SQLAlchemy is not instrumented, and slow audit writes are invisible in Jaeger.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    assert any(span.name.startswith("SELECT") for span in spans.get_finished_spans())


def test_t210_run_with_calls_cannot_be_deleted(engine: Engine) -> None:
    # Red when: deleting a pipeline_run cascades, and a run's paid calls vanish from the audit
    # and from T2.11's sums (review 🟡1: RESTRICT, not CASCADE).
    with Session(engine) as session:
        run = new_run()
        session.add(run)
        session.flush()
        session.add(new_call(run))
        session.flush()
        with pytest.raises(IntegrityError):
            session.execute(text("DELETE FROM pipeline_run WHERE id = :id"), {"id": run.id})
        session.rollback()


def test_t210_llm_call_keeps_the_stop_reason(engine: Engine) -> None:
    # Review 🟢4: an output cut at max_tokens is told apart from a malformed one.
    with Session(engine) as session:
        run = new_run()
        session.add(run)
        session.flush()
        call = new_call(run, stop_reason="max_tokens")
        session.add(call)
        session.flush()
        session.expire_all()
        stored = session.get(LlmCall, call.id)
        assert stored is not None and stored.stop_reason == "max_tokens"
        session.rollback()


def test_t74_syllabus_toc_task_is_accepted_and_unknown_refused(engine: Engine) -> None:
    # Red when: migration 0007 or the model leaves 'syllabus_toc' out of the task CHECKs.
    with Session(engine) as session:
        run = new_run(task="syllabus_toc")
        session.add(run)
        session.flush()
        session.add(new_call(run, task="syllabus_toc"))
        session.flush()
        session.rollback()
    with Session(engine) as session:
        session.add(new_run(task="syllabus_unknown"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


@pytest.mark.parametrize("task", ["draft_units", "read_notes"])
def test_t77_draft_units_and_read_notes_tasks_are_accepted(engine: Engine, task: str) -> None:
    # Red when: migration 0008 or the model leaves the task out of the task CHECKs.
    with Session(engine) as session:
        run = new_run(task=task)
        session.add(run)
        session.flush()
        session.add(new_call(run, task=task))
        session.flush()
        session.rollback()


@pytest.mark.parametrize("task", T83_TASKS)
def test_t7m3_practice_and_bank_tasks_are_accepted(engine: Engine, task: str) -> None:
    # Red when: migration 0009 or the model leaves the task out of the task CHECKs.
    with Session(engine) as session:
        run = new_run(task=task)
        session.add(run)
        session.flush()
        session.add(new_call(run, task=task))
        session.flush()
        session.rollback()


@pytest.mark.parametrize("task", T96_TASKS)
def test_t96b_generated_question_tasks_are_accepted(engine: Engine, task: str) -> None:
    # Red when: migration 0010 or the model leaves the task out of the task CHECKs.
    with Session(engine) as session:
        run = new_run(task=task)
        session.add(run)
        session.flush()
        session.add(new_call(run, task=task))
        session.flush()
        session.rollback()


def test_t7m3_new_tasks_are_in_the_literal_and_the_model_table() -> None:
    # Red when: Task, TASKS, the model's TASKS and the default model table drift apart.
    from ai_service.config import Settings
    from ai_service.db.models import TASKS as MODEL_TASKS
    from ai_service.llm.types import TASKS as LITERAL_TASKS

    assert set(T83_TASKS) <= set(LITERAL_TASKS)
    assert set(LITERAL_TASKS) == MODEL_TASKS
    assert set(Settings.model_fields["llm_models"].default_factory()) == MODEL_TASKS  # type: ignore[call-arg,misc]
