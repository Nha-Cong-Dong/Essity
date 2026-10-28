from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_service.llm.pricing import PRICES
from ai_service.llm.types import TASKS

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
    # redis://... for the event consumer (T4.3). Optional: the grading API does not need Redis,
    # and the consumer refuses to start without it. Secret because it may hold a password.
    redis_url: SecretStr | None = None

    # The object storage the document indexer reads and writes (T4.7), AI_S3_*. Optional like
    # Redis: only the consumer needs it, and it refuses to start without it.
    s3_endpoint: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"

    # Who grades (T2.10). The only place a provider is chosen: the task table picks models.
    # No default: a deploy must say it. `fake` grades without a model and only runs in local and
    # test (R41); `disabled` starts without a key and answers 503 grading_disabled.
    llm_provider: LlmProvider
    # Anthropic's own variable name, no AI_ prefix. Required when llm_provider is anthropic.
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY", validate_default=True
    )

    # Task -> model for a real provider (ADR-0010), changeable without code: AI_LLM_MODELS as
    # JSON. Every task needs a model and every model a price, or the service refuses to start.
    llm_models: dict[str, str] = Field(
        default_factory=lambda: {
            "grade": "claude-haiku-5-5",
            "extract_session": "claude-haiku-5-5",
        },
        validate_default=True,
    )

    # Per-user AI cost quota in USD (T2.11, ADR-0010). Proposed defaults, waiting for the owner to
    # settle them (T6.6): a grade costs about 0.0007 USD, so 0.20 a day is some 250 grades, plenty
    # for one person; the whole system's LLM budget is about 10 USD a month (PRD Q8). Grading
    # stops at `daily x hard_cap_factor` (a day) or `monthly x hard_cap_factor` (a month);
    # other tasks, such as indexing a document, wait at the plain limit.
    quota_daily_usd: Decimal = Field(default=Decimal("0.20"), gt=0, allow_inf_nan=False)
    quota_monthly_usd: Decimal = Field(
        default=Decimal("2.00"), gt=0, allow_inf_nan=False, validate_default=True
    )
    quota_hard_cap_factor: Decimal = Field(default=Decimal(3), ge=1, allow_inf_nan=False)

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

    @field_validator("llm_models")
    @classmethod
    def _every_task_has_a_priced_model(cls, models: dict[str, str]) -> dict[str, str]:
        missing = [task for task in TASKS if task not in models]
        if missing:
            raise ValueError(f"llm_models has no model for {missing}")
        unpriced = sorted({model for model in models.values() if model not in PRICES})
        if unpriced:
            raise ValueError(f"llm_models names models with no price: {unpriced}")
        return models

    @field_validator("quota_monthly_usd")
    @classmethod
    def _a_month_holds_a_day(cls, monthly: Decimal, info: ValidationInfo) -> Decimal:
        daily = info.data.get("quota_daily_usd")
        if daily is not None and daily > monthly:
            raise ValueError("quota_daily_usd is above quota_monthly_usd")
        return monthly

    @property
    def grading_enabled(self) -> bool:
        return self.llm_provider != "disabled"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # fields come from the environment
