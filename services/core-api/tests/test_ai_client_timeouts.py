"""T2.13 (plan D-5): a grading call may take 10 s, a ping 2 s. Red when: the default timeout stays
2 s (every grading call would time out) or a ping waits as long as a grading call."""

import httpx2

from core_api.clients.ai_client import PING_TIMEOUT_SECONDS, AiServiceClient
from core_api.config import Settings


def test_t213_default_ai_service_timeout_is_ten_seconds() -> None:
    assert Settings.model_fields["ai_service_timeout_seconds"].default == 10.0


def test_t213_ping_keeps_its_own_short_timeout() -> None:
    seen: list[object] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.extensions["timeout"])
        return httpx2.Response(200, json={"status": "ok"})

    client = AiServiceClient(
        httpx2.Client(base_url="http://ai", timeout=10.0, transport=httpx2.MockTransport(handler))
    )
    client.ping()
    assert seen[0]["read"] == PING_TIMEOUT_SECONDS == 2.0  # type: ignore[index]
