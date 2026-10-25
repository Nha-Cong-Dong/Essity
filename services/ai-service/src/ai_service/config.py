from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments where the fake grader may run (R41).
DEV_ENVIRONMENTS = frozenset({"local", "test"})

LlmProvider = Literal["anthropic", "fake", "disabled"]


class DatabaseSettings(BaseSettings):
    """What migrations need, and nothing more: `alembic upgrade` must not need API secrets."""

    model_config = SettingsConfigDict(env_prefix="AI_", env_file=".env", extra="ignore")

    # postgresql+psycopg://user:password@host:5432/ai. Secret because it holds the password;
    # no default, so a missing database is a startup error rather than a surprise later.
    database_url: SecretStr


class Settings(DatabaseSettings):
    # No default (R04): a forgotten AI_ENVIRONMENT is a startup error. Compose sets local.
    environment: Literal["local", "test", "staging", "production"]
    log_level: str = "INFO"
    # Shared secret core-api sends in X-Service-Token. No default: the service refuses to start
    # without one rather than run unprotected.
    service_token: SecretStr = Field(min_length=32)

    # Who grades (T2.10). The only place a provider is chosen: the task table picks models.
    # No default: a deploy must say it. `fake` grades without a model and only runs in local and
    # test (R41); `disabled` starts without a key and answers 503 grading_disabled.
    llm_provider: LlmProvider
    # Anthropic's own variable name, no AI_ prefix. Required when llm_provider is anthropic.
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY", validate_default=True
    )

    # Field validators, not a model one: a model validator's error prints the whole input,
    # secrets included, to the startup traceback.
    @field_validator("llm_provider")
    @classmethod
    def _fake_only_in_dev(cls, provider: LlmProvider, info: ValidationInfo) -> LlmProvider:
        # A missing or unknown environment is not in info.data: then the fake is refused too.
        if provider == "fake" and info.data.get("environment") not in DEV_ENVIRONMENTS:
            raise ValueError("llm_provider fake runs only in local and test")
        return provider

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def _blank_key_is_unset(cls, key: object) -> object:
        # Compose passes an unset variable as "".
        return None if isinstance(key, str) and not key.strip() else key

    @field_validator("anthropic_api_key")
    @classmethod
    def _anthropic_needs_a_key(
        cls, key: SecretStr | None, info: ValidationInfo
    ) -> SecretStr | None:
        if key is None and info.data.get("llm_provider") == "anthropic":
            raise ValueError("anthropic_api_key (ANTHROPIC_API_KEY) is required for anthropic")
        return key

    @property
    def grading_enabled(self) -> bool:
        return self.llm_provider != "disabled"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # fields come from the environment
