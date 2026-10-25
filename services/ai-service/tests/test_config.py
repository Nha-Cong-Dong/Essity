"""R04, R30: ai-service starts only when told which environment it is in, and never serves docs."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_service.config import Settings
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER


def test_r04_environment_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    # Red when: environment keeps a default, and a forgotten AI_ENVIRONMENT runs as local.
    monkeypatch.delenv("AI_ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError, match="environment"):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_r04_environment_must_be_one_it_knows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_ENVIRONMENT", "prod")
    with pytest.raises(ValidationError, match="environment"):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_r30_docs_and_openapi_are_always_off(service_token: str, path: str) -> None:
    # Red when: FastAPI(...) keeps a docs route; with a valid token it would answer 200.
    client = TestClient(create_app())
    assert client.get(path, headers={SERVICE_TOKEN_HEADER: service_token}).status_code == 404


# --- T2.10: which LLM provider grades, decided at startup (R41) ---

# Not shaped like a real key (gitleaks), and never sent anywhere: no test calls Anthropic.
FAKE_KEY = "test-anthropic-key-not-real"


def settings_for(
    monkeypatch: pytest.MonkeyPatch, environment: str, provider: str | None, key: str | None
) -> Settings:
    monkeypatch.setenv("AI_ENVIRONMENT", environment)
    if provider is None:
        monkeypatch.delenv("AI_LLM_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("AI_LLM_PROVIDER", provider)
    if key is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    return Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_t210_llm_provider_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    # Red when: llm_provider gets a default, and a deploy that forgets it grades with that one.
    with pytest.raises(ValidationError, match="llm_provider"):
        settings_for(monkeypatch, "test", None, None)


def test_t210_llm_provider_must_be_one_it_knows(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="llm_provider"):
        settings_for(monkeypatch, "test", "openai", None)


@pytest.mark.parametrize("environment", ["local", "test"])
def test_t210_fake_provider_runs_in_dev(monkeypatch: pytest.MonkeyPatch, environment: str) -> None:
    assert settings_for(monkeypatch, environment, "fake", None).llm_provider == "fake"


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_r41_fake_refuses_start_outside_local_test(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    # Red when: the fake grader is accepted outside local/test, and real learners get grades
    # that no model read. Goes through the app's startup (lifespan), not just Settings().
    monkeypatch.setenv("AI_ENVIRONMENT", environment)
    monkeypatch.setenv("AI_LLM_PROVIDER", "fake")
    with pytest.raises(ValidationError, match="llm_provider"), TestClient(create_app()):
        pass


@pytest.mark.parametrize("key", [None, "", "   "])
def test_t210_anthropic_needs_an_api_key(monkeypatch: pytest.MonkeyPatch, key: str | None) -> None:
    # Red when: anthropic starts without a key (or with a blank one) and every grade fails.
    with pytest.raises(ValidationError, match="anthropic_api_key"):
        settings_for(monkeypatch, "production", "anthropic", key)


def test_t210_anthropic_with_a_key_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for(monkeypatch, "production", "anthropic", FAKE_KEY)
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == FAKE_KEY


def test_t210_api_key_is_not_in_the_settings_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    # Red when: the key is a plain str, and any log of the settings prints it.
    settings = settings_for(monkeypatch, "production", "anthropic", FAKE_KEY)
    assert FAKE_KEY not in repr(settings)
    assert FAKE_KEY not in str(settings.model_dump())


def test_t210_disabled_starts_anywhere_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # T0.13 must be able to deploy before the user turns a key on.
    assert settings_for(monkeypatch, "production", "disabled", None).llm_provider == "disabled"
