import pytest
from fastapi.testclient import TestClient

from ai_service.main import create_app


def test_healthz_returns_ok_without_token() -> None:
    response = TestClient(create_app()).get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize(
    ("provider", "grading"),
    [("fake", "enabled"), ("anthropic", "enabled"), ("disabled", "disabled")],
)
def test_t210_healthz_says_whether_grading_is_on(
    monkeypatch: pytest.MonkeyPatch, provider: str, grading: str
) -> None:
    # Red when: /healthz hides that grading is off, and a deploy without a key looks healthy
    # while every answer fails to be graded.
    monkeypatch.setenv("AI_LLM_PROVIDER", provider)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key-not-real")
    response = TestClient(create_app()).get("/healthz")
    assert response.json() == {"status": "ok", "grading": grading}
