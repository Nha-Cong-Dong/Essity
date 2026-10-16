from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from ai_service.api import health, ping
from ai_service.config import get_settings
from ai_service.logging import configure_logging, log_requests
from ai_service.security import require_service_token
from ai_service.telemetry import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging("ai-service", get_settings().log_level)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="ai-service", lifespan=lifespan)
    app.middleware("http")(require_service_token)
    # Added last, so it runs first: rejected requests are logged too, with their request id.
    app.middleware("http")(log_requests)
    app.include_router(health.router)
    app.include_router(ping.router)
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
