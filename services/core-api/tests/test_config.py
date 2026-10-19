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


def test_outside_local_an_https_web_url_is_accepted() -> None:
    assert settings(environment="production", web_base_url="https://essity.example/").web_base_url
