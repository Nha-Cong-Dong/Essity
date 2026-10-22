from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    # No default (R04): a forgotten AI_ENVIRONMENT is a startup error. Compose sets local.
    environment: Literal["local", "test", "staging", "production"]
    log_level: str = "INFO"
    # Shared secret core-api sends in X-Service-Token. No default: the service refuses to start
    # without one rather than run unprotected.
    service_token: SecretStr = Field(min_length=32)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # fields come from the environment
