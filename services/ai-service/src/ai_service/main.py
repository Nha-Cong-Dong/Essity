from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from ai_service.api import grade, health, ping
from ai_service.config import get_settings
from ai_service.db.session import get_session_factory
from ai_service.llm.client import LlmClient, build_adapter
from ai_service.logging import configure_logging, log_requests
from ai_service.security import require_service_token
from ai_service.tasks.grade import fake_grade, load_prompt
from ai_service.telemetry import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Settings are validated here: a bad provider or an unpriced model stops the startup.
    settings = get_settings()
    configure_logging("ai-service", settings.log_level)
    # A missing prompt file stops the startup instead of failing the first grade.
    load_prompt()
    adapter = build_adapter(settings, {"grade": fake_grade})
    app.state.llm_client = (
        None
        if adapter is None
        else LlmClient(adapter, get_session_factory(), models=settings.llm_models)
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
