from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORE_", env_file=".env", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"

    ai_service_url: str = "http://127.0.0.1:8001"
    # Sent to ai-service in X-Service-Token. No default: core-api refuses to start without one,
    # the same rule ai-service applies on its side.
    ai_service_token: SecretStr = Field(min_length=32)
    # Below web's 3 s timeout for core-api, so a hung ai-service is reported as such
    # instead of web timing out and blaming core-api.
    ai_service_timeout_seconds: float = Field(default=2.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # fields come from the environment
