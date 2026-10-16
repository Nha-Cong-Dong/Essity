import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_service.config import Settings
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER, is_valid_service_token


@pytest.fixture
def client() -> TestClient:
    app: FastAPI = create_app()

    @app.get("/v1/probe")
    def probe() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    return TestClient(app)


def test_missing_token_is_rejected(client: TestClient) -> None:
    assert client.get("/v1/probe").status_code == 401


def test_wrong_token_is_rejected(client: TestClient) -> None:
    response = client.get("/v1/probe", headers={SERVICE_TOKEN_HEADER: "wrong-token"})
    assert response.status_code == 401


def test_correct_token_is_accepted(client: TestClient, service_token: str) -> None:
    response = client.get("/v1/probe", headers={SERVICE_TOKEN_HEADER: service_token})
    assert response.status_code == 200


def test_openapi_docs_require_token(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 401


def test_non_ascii_token_is_rejected_not_crashing(service_token: str) -> None:
    assert not is_valid_service_token("tökén", service_token)


def test_service_refuses_short_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", "short")
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


def test_service_refuses_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_SERVICE_TOKEN")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
