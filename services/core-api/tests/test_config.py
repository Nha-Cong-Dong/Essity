"""Settings that must fail closed: core-api refuses to start rather than run misconfigured."""

import pytest
from pydantic import ValidationError

from core_api.config import Settings


def settings(**values: str) -> Settings:
    # Required fields (database, Redis, AI token) come from the test environment (conftest.py).
    return Settings(**values)  # pyright: ignore[reportArgumentType]


def test_local_may_use_the_default_web_url() -> None:
    assert settings(environment="local").web_base_url == "http://localhost:3000"


@pytest.mark.parametrize(
    "values",
    [
        {"environment": "production"},  # forgot to set it: links would point at localhost
        {"environment": "production", "web_base_url": "http://essity.example"},  # tokens in clear
        {"environment": "staging", "web_base_url": "essity.example"},
    ],
)
def test_outside_local_the_web_url_must_be_set_and_https(values: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="web_base_url"):
        settings(**values)


LOG_HASH_KEY = "log-hash-key-for-tests-0123456789abcdef"


# Everything production needs, set as it should be (R04): each test below breaks one of them.
PRODUCTION = {
    "environment": "production",
    "web_base_url": "https://essity.example/",
    "log_hash_key": LOG_HASH_KEY,
    "web_token": "web-token-for-tests-0123456789abcdefgh",
    "smtp_host": "smtp.essity.example",
    "smtp_username": "essity",
    "smtp_password": "smtp-password-for-tests",
    "smtp_starttls": "true",
    "email_from": "no-reply@essity.example",
    "ai_service_url": "http://ai-service:8001",
}


def test_outside_local_an_https_web_url_is_accepted() -> None:
    assert settings(**PRODUCTION).web_base_url


def test_log_hash_key_required_outside_local_and_test() -> None:
    # Without a key, hashed IPs in the security log could be reversed (A13, T1.8).
    with pytest.raises(ValidationError, match="log_hash_key"):
        settings(environment="production", web_base_url="https://essity.example/")


def test_log_hash_key_must_be_long() -> None:
    with pytest.raises(ValidationError, match="log_hash_key"):
        settings(log_hash_key="short")


def test_local_works_without_a_log_hash_key() -> None:
    assert settings(environment="local").log_hash_key is None
    assert settings(environment="local", log_hash_key="").log_hash_key is None  # from Compose


def test_a_settings_error_never_shows_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    # The startup traceback goes to stderr, past the log formatter (ADR-0013).
    monkeypatch.setenv("CORE_AI_SERVICE_TOKEN", "ai-token-that-must-never-be-printed-anywhere")
    monkeypatch.setenv("CORE_DATABASE_URL", "postgresql+psycopg://core:db-password-secret@db/core")
    with pytest.raises(ValidationError) as error:
        settings(environment="production")
    message = str(error.value)
    # Pydantic shows the start and end of the input; which secret lands there depends on field
    # order, so no dump of the whole input may appear at all.
    assert "input_value={" not in message
    assert "printed-anywhere" not in message
    assert "db-password-secret" not in message


def test_r04_environment_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    # Red when: environment keeps a default, and a forgotten variable runs production as local.
    monkeypatch.delenv("CORE_ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError, match="environment"):
        Settings()  # pyright: ignore[reportCallIssue]


def test_r04_environment_must_be_one_it_knows() -> None:
    with pytest.raises(ValidationError, match="environment"):
        settings(**{**PRODUCTION, "environment": "prod"})


def test_r04_an_unknown_environment_is_treated_as_production() -> None:
    # Red when: the other rules fall back to local's when environment is wrong (plan D1).
    with pytest.raises(ValidationError) as error:
        settings(environment="prod")
    assert "web_base_url" in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("web_token", ""),
        ("smtp_host", "127.0.0.1"),
        ("smtp_host", "127.8.8.8"),
        ("smtp_host", "localhost"),
        ("smtp_host", "::1"),
        ("smtp_host", "0.0.0.0"),
        ("email_from", "no-reply@localhost"),
        ("email_from", "Essity <no-reply@localhost>"),
        ("email_from", "no-reply@localhost."),
        ("web_base_url", "https://localhost:3000"),
        ("web_base_url", "https://127.0.0.1/"),
        ("smtp_starttls", "false"),  # a password sent in clear
        ("ai_service_url", "http://127.0.0.1:8001"),
        ("ai_service_url", "http://localhost:8001"),
    ],
)
def test_r04_outside_dev_a_local_value_is_refused(field: str, value: str) -> None:
    # Red when: production starts with a value that only works on a developer's machine.
    with pytest.raises(ValidationError, match=field):
        settings(**{**PRODUCTION, field: value})


def test_r04_staging_follows_the_production_rules() -> None:
    with pytest.raises(ValidationError, match="smtp_host"):
        settings(**{**PRODUCTION, "environment": "staging", "smtp_host": "127.0.0.1"})


def test_r04_starttls_is_required_even_without_a_login() -> None:
    # Red when: a server without login (Mailpit, from .env.example) passes outside local: the
    # one-time links in verification and reset emails would travel in clear (review 8489155).
    values = {**PRODUCTION, "smtp_starttls": "false"}
    del values["smtp_username"], values["smtp_password"]
    with pytest.raises(ValidationError, match="smtp_starttls"):
        settings(**values)


def test_r04_env_example_values_are_refused_in_production() -> None:
    # The SMTP lines of .env.example with only the environment changed.
    with pytest.raises(ValidationError, match="smtp_starttls"):
        settings(
            **{**PRODUCTION, "smtp_host": "mailpit", "smtp_port": "1025", "smtp_starttls": "false"}
        )


def test_r04_local_keeps_its_defaults() -> None:
    local = settings(environment="local")
    assert (local.smtp_host, local.email_from) == ("127.0.0.1", "no-reply@localhost")


def test_r04_error_names_the_variable_and_no_secret() -> None:
    # Red when: the startup error leaves out which setting is wrong, or prints a secret (P2).
    with pytest.raises(ValidationError) as error:
        settings(**{**PRODUCTION, "smtp_starttls": "false", "smtp_host": "127.0.0.1"})
    message = str(error.value)
    assert "smtp_starttls" in message and "smtp_host" in message
    for secret in ("smtp-password-for-tests", "web-token-for-tests", "log-hash-key-for-tests"):
        assert secret not in message
