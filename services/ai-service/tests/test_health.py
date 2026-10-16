from fastapi.testclient import TestClient

from ai_service.main import app

client = TestClient(app)


def test_healthz_returns_ok_without_token() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
