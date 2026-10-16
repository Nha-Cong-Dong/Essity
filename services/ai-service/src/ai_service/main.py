from fastapi import FastAPI

from ai_service.api import health, ping
from ai_service.security import require_service_token


def create_app() -> FastAPI:
    app = FastAPI(title="ai-service")
    app.middleware("http")(require_service_token)
    app.include_router(health.router)
    app.include_router(ping.router)
    return app


app = create_app()
