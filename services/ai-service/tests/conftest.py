from collections.abc import Iterator

import pytest

from ai_service.config import get_settings

TEST_SERVICE_TOKEN = "test-service-token-0123456789abcdef"


@pytest.fixture
def service_token() -> str:
    return TEST_SERVICE_TOKEN


@pytest.fixture(autouse=True)
def service_token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AI_ENVIRONMENT", "test")
    monkeypatch.setenv("AI_SERVICE_TOKEN", TEST_SERVICE_TOKEN)
    monkeypatch.setenv("AI_LLM_PROVIDER", "fake")
    # A real key in the developer's shell must never reach a test.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
