"""T2.10: database `ai` (pipeline_run, llm_call). Runs on the real test PostgreSQL (conftest)."""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import ai_service.main  # noqa: F401  # pyright: ignore[reportUnusedImport]  # installs tracing
from ai_service.db.base import NAMING_CONVENTION, Base
from ai_service.db.models import LlmCall, PipelineRun
from ai_service.telemetry import RedactingSpanExporter

TABLES = {"pipeline_run", "llm_call"}


def table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def test_t210_migrations_go_down_to_base_and_back_up(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: a migration's downgrade leaves a table behind or its upgrade cannot run twice.
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


def test_t210_query_creates_a_span(engine: Engine) -> None:
    # Red when: SQLAlchemy is not instrumented, and slow audit writes are invisible in Jaeger.
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(RedactingSpanExporter(exporter)))
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    assert any(span.name.startswith("SELECT") for span in exporter.get_finished_spans())
