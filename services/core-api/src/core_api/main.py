from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from core_api.api import (
    attempts,
    auth,
    documents,
    drafts,
    export,
    grades,
    health,
    me,
    outline,
    ping,
    practice,
    practice_types,
    review_sessions,
    session_confirm,
    session_notes,
    sessions,
    stats,
    subjects,
    submissions,
    suggestions,
    today,
    units,
)
from core_api.api.errors import install_validation_handler
from core_api.clients.ai_client import AiServiceClient
from core_api.clients.storage import S3Storage
from core_api.config import get_settings
from core_api.logging import configure_logging, log_requests
from core_api.security.rate_limit import install_rate_limit_handlers
from core_api.telemetry import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Reading settings here makes a missing or short AI service token fail at startup.
    settings = get_settings()
    configure_logging("core-api", settings.log_level)
    ai_client = AiServiceClient.from_settings(settings)
    app.state.ai_client = ai_client
    # Builds the clients only: no call to the store, so startup does not wait on it.
    app.state.storage = S3Storage.from_settings(settings)
    try:
        yield
    finally:
        ai_client.close()


# Before uvicorn logs "Started server process", so every line is JSON. The lifespan then
# applies the configured level.
configure_logging("core-api", "INFO")
configure_tracing("core-api")

# Internal service (ARCH §3): no docs or schema route in any environment (R30). The web client's
# schema comes from app.openapi() (scripts/openapi_export.py), which does not need the route.
app = FastAPI(title="core-api", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.middleware("http")(log_requests)
install_rate_limit_handlers(app)
install_validation_handler(app)
app.include_router(health.router)
app.include_router(ping.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(subjects.router)
app.include_router(documents.router)
app.include_router(outline.router)
app.include_router(today.router)
app.include_router(review_sessions.router)
app.include_router(attempts.router)
app.include_router(grades.router)
app.include_router(practice.router)
app.include_router(practice_types.router)
app.include_router(units.router)
app.include_router(sessions.router)
app.include_router(session_confirm.router)
app.include_router(session_notes.router)
app.include_router(submissions.router)
app.include_router(drafts.router)
app.include_router(stats.router)
app.include_router(suggestions.router)
app.include_router(export.router)
# Outermost middleware: the request span is open while log_requests writes its line.
FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz", exclude_spans=["receive", "send"])
