from fastapi import FastAPI

from core_api.api import health

app = FastAPI(title="core-api")
app.include_router(health.router)
