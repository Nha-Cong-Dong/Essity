from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments where defaults pointing at localhost are fine.
DEV_ENVIRONMENTS = frozenset({"local", "test"})


class DatabaseSettings(BaseSettings):
    """What migrations need, and nothing more: `alembic upgrade` must not need API secrets."""

    model_config = SettingsConfigDict(env_prefix="CORE_", env_file=".env", extra="ignore")

    # postgresql+psycopg://user:password@host:5432/core. Secret because it holds the password;
    # no default, so a missing database is a startup error rather than a surprise later.
    database_url: SecretStr


class Settings(DatabaseSettings):
    environment: str = "local"
    log_level: str = "INFO"

    # redis://[:password@]host:6379/0. Rate limits (T1.6); a secret if it holds a password.
    redis_url: SecretStr
    # Token web sends in X-Service-Token. Only a request carrying it may say which IP the user
    # has (security.client_ip). Unset: core-api never trusts a client IP header.
    web_token: SecretStr | None = Field(default=None, min_length=32)

    # Email (T1.5). Locally Mailpit: no TLS, no login, web UI on http://localhost:8025.
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    email_from: str = "no-reply@localhost"
    # Where links in emails point: the web app, the only service on the internet (ARCH §3).
    # Outside local and test it must be set, and https: the links carry one-time tokens.
    web_base_url: str = "http://localhost:3000"

    ai_service_url: str = "http://127.0.0.1:8001"
    # Sent to ai-service in X-Service-Token. No default: core-api refuses to start without one,
    # the same rule ai-service applies on its side.
    ai_service_token: SecretStr = Field(min_length=32)
    # Below web's 3 s timeout for core-api, so a hung ai-service is reported as such
    # instead of web timing out and blaming core-api.
    ai_service_timeout_seconds: float = Field(default=2.0, gt=0)

    @model_validator(mode="after")
    def _web_url_fits_environment(self) -> Self:
        if self.environment not in DEV_ENVIRONMENTS and (
            "web_base_url" not in self.model_fields_set
            or not self.web_base_url.startswith("https://")
        ):
            raise ValueError("web_base_url must be set to an https:// URL outside local and test")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # fields come from the environment
