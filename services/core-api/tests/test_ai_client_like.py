"""T9.6b: core-api's call to ai-service's POST /v1/generate-like. One try, no retry (US-17 AC6);
every failure is a NotGraded with a stable code, never ai-service's body (ADR-0013)."""

import uuid

import httpx2

from core_api.clients.ai_client import AiServiceClient, NotGraded
from core_api.clients.like_contract import LikeReply

BASE = {"prompt_version": "v1", "run_id": str(uuid.uuid4()), "llm_call_id": None}
KEPT = {
    "prompt": "Q?",
    "reference_answer": "A",
    "rubric": "R",
    "card_ids": [str(uuid.uuid4())],
}


def client_answering(answer: httpx2.Response | Exception) -> tuple[AiServiceClient, list[bytes]]:
    seen: list[bytes] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.content)
        if isinstance(answer, Exception):
            raise answer
        return answer

    http = httpx2.Client(
        base_url="http://ai", timeout=10.0, transport=httpx2.MockTransport(handler)
    )
    return AiServiceClient(http), seen


def test_generate_like_parses_the_reply_in_one_call() -> None:
    # Red when: the strict contract rejects what ai-service sends, or a second call is made.
    body = {**BASE, "status": "ok", "kept": [KEPT], "dropped": [{"reason": "judge_j3_generic"}]}
    client, seen = client_answering(httpx2.Response(200, json=body))
    reply = client.generate_like({"cards": []})
    assert isinstance(reply, LikeReply) and reply.status == "ok" and len(reply.kept) == 1
    assert len(seen) == 1


def test_a_reply_outside_the_contract_is_not_trusted() -> None:
    # Red when: an extra field or an oversized candidate from ai-service is accepted.
    for body in (
        {**BASE, "status": "ok", "kept": [{**KEPT, "extra": 1}]},
        {**BASE, "status": "ok", "kept": [{**KEPT, "prompt": "x" * 501}]},
        {**BASE, "status": "maybe"},
    ):
        client, _ = client_answering(httpx2.Response(200, json=body))
        reply = client.generate_like({})
        assert isinstance(reply, NotGraded) and reply.reason == "response_schema"


def test_failures_are_stable_codes_and_never_retried() -> None:
    # Red when: a failure is retried, or ai-service's body reaches the reason.
    cases: list[tuple[httpx2.Response | Exception, str, str]] = [
        (
            httpx2.Response(503, json={"code": "grading_disabled", "x": "SECRET"}),
            "disabled",
            "grading_disabled",
        ),
        (httpx2.Response(429, json={"code": "quota_hard_cap"}), "quota", "quota_hard_cap"),
        (httpx2.Response(422, json={"code": "invalid_request"}), "invalid", "invalid_request"),
        (httpx2.Response(500, text="SECRET"), "unavailable", "server_error"),
        (httpx2.ReadTimeout("slow"), "unavailable", "timeout"),
    ]
    for answer, failure, reason in cases:
        client, seen = client_answering(answer)
        reply = client.generate_like({})
        assert reply == NotGraded(failure, reason)  # type: ignore[arg-type]
        assert len(seen) == 1
