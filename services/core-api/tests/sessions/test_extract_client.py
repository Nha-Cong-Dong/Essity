"""T4.12: core-api's call to ai-service's POST /v1/extract-session. One try, never a retry: the
learner is waiting at the card and the manual form is the fallback (plan "Endpoint")."""

import uuid

import httpx2
import pytest

from core_api.clients.ai_client import AiServiceClient, Extracted, NotExtracted

PAYLOAD = {"description": "học chương 3"}
DOC = uuid.uuid4()
COMMON = {
    "provider": "fake",
    "model": None,
    "prompt_version": "v1",
    "run_id": str(uuid.uuid4()),
    "llm_call_id": None,
}
PROPOSED = COMMON | {
    "status": "proposed",
    "studied_on": "2026-10-28",
    "ranges": [
        {
            "document_id": str(DOC),
            "start_page": 3,
            "end_page": 9,
            "start_label": "1",
            "end_label": "7",
            "depth": "deep",
            "sections": ["Chương 3"],
            "basis_assumed_file": False,
        }
    ],
}


def client_answering(*answers: httpx2.Response | Exception) -> tuple[AiServiceClient, list[object]]:
    seen: list[object] = []
    script = iter(answers)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        answer = next(script)
        if isinstance(answer, Exception):
            raise answer
        return answer

    http = httpx2.Client(base_url="http://ai", transport=httpx2.MockTransport(handler))
    return AiServiceClient(http), seen


def test_a_proposed_answer_is_parsed() -> None:
    client, seen = client_answering(httpx2.Response(200, json=PROPOSED))
    outcome = client.extract_session(PAYLOAD, timeout=4.0)
    assert isinstance(outcome, Extracted)
    assert outcome.response.status == "proposed"
    assert outcome.response.ranges[0].document_id == DOC
    assert len(seen) == 1


def test_clarify_and_note_only_answers_are_parsed() -> None:
    clarify = COMMON | {
        "status": "clarify",
        "question": "Chương 4 của tài liệu nào?",
        "reason": "ambiguous_document",
        "candidate_document_ids": [str(DOC)],
    }
    note_only = COMMON | {"status": "note_only", "studied_on": None}
    client, _ = client_answering(
        httpx2.Response(200, json=clarify), httpx2.Response(200, json=note_only)
    )
    first = client.extract_session(PAYLOAD, timeout=4.0)
    second = client.extract_session(PAYLOAD, timeout=4.0)
    assert isinstance(first, Extracted) and first.response.status == "clarify"
    assert isinstance(second, Extracted) and second.response.status == "note_only"


@pytest.mark.parametrize(
    ("answer", "failure"),
    [
        (httpx2.Response(503, json={"code": "quota_hard_cap"}), "quota"),
        (httpx2.Response(503, json={"code": "grading_disabled"}), "disabled"),
        (httpx2.Response(503, json={"code": "llm_unavailable"}), "unavailable"),
        (httpx2.Response(500, text="boom"), "unavailable"),
        (httpx2.Response(422, json={"code": "invalid_request"}), "invalid"),
        (httpx2.Response(200, json={"status": "proposed"}), "invalid"),
        (httpx2.Response(200, json=PROPOSED | {"extra": 1}), "invalid"),
        (httpx2.ReadTimeout("slow"), "unavailable"),
        (httpx2.ConnectError("down"), "unavailable"),
    ],
)
def test_failures_map_to_a_code_and_are_never_retried(
    answer: httpx2.Response | Exception, failure: str
) -> None:
    client, seen = client_answering(answer, httpx2.Response(200, json=PROPOSED))
    outcome = client.extract_session(PAYLOAD, timeout=4.0)
    assert isinstance(outcome, NotExtracted)
    assert outcome.failure == failure
    assert len(seen) == 1


def test_the_timeout_asked_is_the_one_used() -> None:
    client, seen = client_answering(httpx2.Response(200, json=PROPOSED))
    client.extract_session(PAYLOAD, timeout=1.5)
    request = seen[0]
    assert isinstance(request, httpx2.Request)
    assert request.extensions["timeout"]["read"] == 1.5
    assert request.extensions["timeout"]["connect"] == 1.0


def test_no_body_reaches_the_log(caplog: pytest.LogCaptureFixture) -> None:
    secret = "mô tả riêng tư của người học"
    client, _ = client_answering(httpx2.Response(500, text=secret))
    with caplog.at_level("DEBUG"):
        client.extract_session(PAYLOAD, timeout=4.0)
    assert secret not in caplog.text
    assert "học chương 3" not in caplog.text
