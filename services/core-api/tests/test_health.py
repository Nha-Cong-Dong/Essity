import pytest
from fastapi.testclient import TestClient

from core_api.config import Settings
from core_api.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORE_ENVIRONMENT", "test")
    assert Settings().environment == "test"  # pyright: ignore[reportCallIssue]
