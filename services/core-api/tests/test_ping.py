"""GET /v1/ping calls ai-service. ai-service is replaced by an httpx2 MockTransport."""

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import PING_TIMEOUT_SECONDS, SERVICE_TOKEN_HEADER, AiServiceClient
from core_api.config import Settings, get_settings
from core_api.main import app

Handler = Callable[[httpx2.Request], httpx2.Response]


@pytest.fixture
def ping_with() -> Iterator[Callable[[Handler], httpx2.Response]]:
    """Call core-api /v1/ping with ai-service answering through `handler`."""
    clients: list[AiServiceClient] = []

    def call(handler: Handler) -> httpx2.Response:
        ai_client = AiServiceClient.from_settings(get_settings(), httpx2.MockTransport(handler))
        clients.append(ai_client)
        app.dependency_overrides[get_ai_client] = lambda: ai_client
        return TestClient(app).get("/v1/ping")

    yield call
    app.dependency_overrides.clear()
    for ai_client in clients:
        ai_client.close()


def ai_ok(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"status": "ok"})


def test_ping_reports_ok_when_ai_service_answers(
    ping_with: Callable[[Handler], httpx2.Response],
) -> None:
    response = ping_with(ai_ok)
    assert response.status_code == 200
    assert response.json() == {"core_api": "ok", "ai_service": "ok"}


def test_ping_calls_ai_service_with_service_token(
    ping_with: Callable[[Handler], httpx2.Response], ai_service_token: str
) -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return ai_ok(request)

    ping_with(handler)
    assert [r.url.path for r in seen] == ["/v1/ping"]
    assert seen[0].headers[SERVICE_TOKEN_HEADER] == ai_service_token


@pytest.mark.parametrize("status", [401, 500, 503])
def test_ping_reports_unavailable_on_error_status(
    ping_with: Callable[[Handler], httpx2.Response], status: int
) -> None:
    response = ping_with(lambda request: httpx2.Response(status))
    assert response.status_code == 503
    assert response.json() == {"core_api": "ok", "ai_service": "unavailable"}


@pytest.mark.parametrize("error", [httpx2.ConnectError("refused"), httpx2.ReadTimeout("too slow")])
def test_ping_reports_unavailable_when_ai_service_unreachable(
    ping_with: Callable[[Handler], httpx2.Response], error: httpx2.TransportError
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise error

    response = ping_with(handler)
    assert response.status_code == 503
    assert response.json() == {"core_api": "ok", "ai_service": "unavailable"}


def test_ai_client_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORE_AI_SERVICE_TIMEOUT_SECONDS", "1.5")
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return ai_ok(request)

    ai_client = AiServiceClient.from_settings(Settings(), httpx2.MockTransport(handler))  # pyright: ignore[reportCallIssue]
    # The configured timeout is the client's default, for grading calls (T2.13 plan D-5); the
    # ping keeps its own short one.
    assert ai_client._http.timeout.read == 1.5  # pyright: ignore[reportPrivateUsage]
    ai_client.ping()
    ai_client.close()
    assert seen[0].extensions["timeout"]["read"] == PING_TIMEOUT_SECONDS


def test_core_api_refuses_short_ai_service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORE_AI_SERVICE_TOKEN", "short")
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


def test_core_api_refuses_missing_ai_service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORE_AI_SERVICE_TOKEN")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_app_startup_fails_without_ai_service_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CORE_AI_SERVICE_TOKEN")
    monkeypatch.chdir(tmp_path)  # no .env to fall back on
    get_settings.cache_clear()
    with pytest.raises(ValidationError), TestClient(app):
        pass
