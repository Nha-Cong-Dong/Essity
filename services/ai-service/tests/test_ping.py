from fastapi.testclient import TestClient

from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER


def test_ping_with_token_returns_ok(service_token: str) -> None:
    response = TestClient(create_app()).get(
        "/v1/ping", headers={SERVICE_TOKEN_HEADER: service_token}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ping_without_token_is_rejected() -> None:
    assert TestClient(create_app()).get("/v1/ping").status_code == 401
