from collections.abc import Iterator

import pytest

from core_api.config import get_settings

TEST_AI_SERVICE_TOKEN = "test-ai-service-token-0123456789abcdef"


@pytest.fixture
def ai_service_token() -> str:
    return TEST_AI_SERVICE_TOKEN


@pytest.fixture(autouse=True)
def ai_service_token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CORE_AI_SERVICE_TOKEN", TEST_AI_SERVICE_TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
