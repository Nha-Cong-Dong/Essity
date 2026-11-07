"""T9.2e: core-api's call to ai-service's POST /v1/parse-command. One try, cut at 8 s, every failure
a `NotGraded` with a stable code, never ai-service's body (ADR-0013); 429 `quota_hard_cap` is the
code that turns the command bar off (US-18 AC8)."""

import uuid

import httpx2
import pytest

from core_api.clients.ai_client import PARSE_COMMAND_SECONDS, AiServiceClient, NotGraded
from core_api.clients.parse_command_contract import ParseCommandReply

OK = {
    "provider": "fake",
    "model": "fake",
    "prompt_version": "v1",
    "run_id": str(uuid.uuid4()),
    "llm_call_id": str(uuid.uuid4()),
    "result": {"kind": "section_exclude", "sections": [str(uuid.uuid4())]},
}


def client_answering(answer: httpx2.Response | Exception) -> tuple[AiServiceClient, list[object]]:
    seen: list[object] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append((request.url.path, request.extensions.get("timeout")))
        if isinstance(answer, Exception):
            raise answer
        return answer

    http = httpx2.Client(base_url="http://ai", transport=httpx2.MockTransport(handler))
    return AiServiceClient(http), seen


def test_parse_command_reads_the_reply_once_with_an_8_second_cut() -> None:
    # Red when: the cut is not 8 s, a second call is made, or the strict contract rejects it.
    client, seen = client_answering(httpx2.Response(200, json=OK))
    reply = client.parse_command({"command": "x"})
    assert isinstance(reply, ParseCommandReply) and reply.result["kind"] == "section_exclude"
    assert len(seen) == 1 and PARSE_COMMAND_SECONDS == 8.0
    path, timeout = seen[0]  # type: ignore[misc]
    assert path == "/v1/parse-command" and timeout["read"] == 8.0


@pytest.mark.parametrize(
    ("answer", "failure"),
    [
        (httpx2.Response(429, json={"code": "quota_hard_cap"}), "quota"),
        (httpx2.Response(503, json={"code": "grading_disabled"}), "disabled"),
        (httpx2.Response(502, json={"code": "parse_command_invalid"}), "invalid"),
        (httpx2.Response(422, json={"detail": []}), "invalid"),
        (httpx2.Response(200, json={"result": 1}), "invalid"),
        (httpx2.ReadTimeout("slow"), "unavailable"),
        (httpx2.ConnectError("down"), "unavailable"),
    ],
)
def test_parse_command_failures_are_codes_not_bodies(
    answer: httpx2.Response | Exception, failure: str
) -> None:
    client, seen = client_answering(answer)
    reply = client.parse_command({"command": "bỏ mục 1"})
    assert isinstance(reply, NotGraded) and reply.failure == failure
    assert len(seen) == 1  # never retried: the command bar waits for one answer
