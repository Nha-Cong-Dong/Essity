from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from core_api.api import auth, health, me, ping, subjects, today
from core_api.api.errors import install_validation_handler
from core_api.clients.ai_client import AiServiceClient
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
app.include_router(today.router)
# Outermost middleware: the request span is open while log_requests writes its line.
FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz", exclude_spans=["receive", "send"])
