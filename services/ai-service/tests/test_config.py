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
