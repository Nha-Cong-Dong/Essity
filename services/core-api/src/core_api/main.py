from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core_api.api import health, ping
from core_api.clients.ai_client import AiServiceClient
from core_api.config import get_settings
from core_api.logging import configure_logging, log_requests


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

app = FastAPI(title="core-api", lifespan=lifespan)
app.middleware("http")(log_requests)
app.include_router(health.router)
app.include_router(ping.router)
