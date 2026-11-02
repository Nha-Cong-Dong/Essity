from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from ai_service.api import (
    extract_session,
    generate_like,
    grade,
    health,
    parse_command,
    ping,
    practice,
    question_bank,
    review_question,
)
from ai_service.config import get_settings
from ai_service.db.session import get_session_factory
from ai_service.llm.client import LlmClient, build_adapter
from ai_service.llm.quota import DbQuotaGuard, QuotaLimits
from ai_service.logging import configure_logging, log_requests
from ai_service.security import require_service_token
from ai_service.tasks import extract_session as extract_task
from ai_service.tasks import generate_like as generate_like_task
from ai_service.tasks import grade_practice as grade_practice_task
from ai_service.tasks import parse_command as parse_task
from ai_service.tasks import question_bank as question_bank_task
from ai_service.tasks.bank_run import fake_parse_question_bank
from ai_service.tasks.grade import fake_grade, load_prompt
from ai_service.tasks.like_run import fake_generate_like, fake_judge_questions
from ai_service.tasks.practice_run import fake_draft_answer, fake_grade_practice
from ai_service.tasks.process_session import fake_questions
from ai_service.telemetry import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Settings are validated here: a bad provider or an unpriced model stops the startup.
    settings = get_settings()
    configure_logging("ai-service", settings.log_level)
    # A missing prompt file stops the startup instead of failing the first grade.
    load_prompt()
    extract_task.load_prompt()
    parse_task.load_prompt()
    grade_practice_task.load_prompt()
    generate_like_task.load_prompt(generate_like_task.GENERATE_TASK)
    generate_like_task.load_prompt(generate_like_task.JUDGE_TASK)
    for name in ("bank_split", "bank_types", "bank_sections"):
        question_bank_task.load_prompt(name)
    adapter = build_adapter(
        settings,
        {
            "grade": fake_grade,
            "extract_session": extract_task.fake_extract,
            "parse_command": parse_task.fake_parse,
            "grade_practice": fake_grade_practice,
            "draft_answer": fake_draft_answer,
            "generate_like": fake_generate_like,
            "judge_questions": fake_judge_questions,
            "generate_questions": fake_questions,
            "parse_question_bank": fake_parse_question_bank,
        },
    )
    sessions = get_session_factory()
    limits = QuotaLimits(
        daily=settings.quota_daily_usd,
        monthly=settings.quota_monthly_usd,
        hard_cap_factor=settings.quota_hard_cap_factor,
    )
    app.state.llm_client = (
        None
        if adapter is None
        else LlmClient(
            adapter,
            sessions,
            models=settings.llm_models,
            quota_guard=DbQuotaGuard(
                sessions, limits, hard_cap_tasks=frozenset({"grade", "extract_session"})
            ),
        )
    )
    yield


def create_app() -> FastAPI:
    # Internal service (ARCH §3): no docs or schema route in any environment (R30).
    app = FastAPI(
        title="ai-service", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.middleware("http")(require_service_token)
    # Added last, so it runs first: rejected requests are logged too, with their request id.
    app.middleware("http")(log_requests)
    app.include_router(health.router)
    app.include_router(ping.router)
    app.include_router(grade.router)
    grade.add_error_handlers(app)
    app.include_router(extract_session.router)
    extract_session.add_error_handlers(app)
    app.include_router(parse_command.router)
    parse_command.add_error_handlers(app)
    app.include_router(practice.router)
    app.include_router(generate_like.router)
    generate_like.add_error_handlers(app)
    app.include_router(review_question.router)
    app.include_router(question_bank.router)
    # Outermost middleware: continues the trace started by core-api (W3C traceparent).
    FastAPIInstrumentor.instrument_app(
        app, excluded_urls="healthz", exclude_spans=["receive", "send"]
    )
    return app


# Before uvicorn logs "Started server process", so every line is JSON. The lifespan then
# applies the configured level.
configure_logging("ai-service", "INFO")
configure_tracing("ai-service")
app = create_app()
