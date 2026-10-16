from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core_api.api import health, ping
from core_api.clients.ai_client import AiServiceClient
from core_api.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Reading settings here makes a missing or short AI service token fail at startup.
    ai_client = AiServiceClient.from_settings(get_settings())
    app.state.ai_client = ai_client
    try:
        yield
    finally:
        ai_client.close()


app = FastAPI(title="core-api", lifespan=lifespan)
app.include_router(health.router)
app.include_router(ping.router)
