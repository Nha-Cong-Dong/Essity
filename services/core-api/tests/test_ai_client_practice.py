"""T8.4: core-api's calls to ai-service's POST /v1/grade-practice and /v1/draft-answer. One try, no
retry; every failure is a `NotGraded` with a stable code, never ai-service's body (ADR-0013)."""

import uuid

import httpx2

from core_api.clients.ai_client import AiServiceClient, NotGraded
from core_api.clients.practice_contract import DraftAnswerReply, PracticeGradeReply

BASE = {"prompt_version": "v1", "run_id": str(uuid.uuid4()), "llm_call_id": None}
GRADED = {
    **BASE,
    "status": "ok",
    "overall": "partial",
    "ideas": [{"verdict": "correct", "anchor": "x"}, {"verdict": "incorrect", "anchor": None}],
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


def test_grade_practice_parses_the_reply() -> None:
    # Red when: the strict contract rejects what ai-service sends, or a second call is made.
    client, seen = client_answering(httpx2.Response(200, json=GRADED))
    reply = client.grade_practice({"question": "q"})
    assert isinstance(reply, PracticeGradeReply)
    assert (reply.status, reply.overall, len(reply.ideas)) == ("ok", "partial", 2)
    assert len(seen) == 1


def test_draft_answer_parses_the_reply() -> None:
    client, _ = client_answering(
        httpx2.Response(
            200, json={**BASE, "status": "ok", "answer": "A", "answer_origin": "ai", "card_ids": []}
        )
    )
    reply = client.draft_answer({"question": "q"})
    assert isinstance(reply, DraftAnswerReply) and reply.answer_origin == "ai"


def test_pending_ai_is_a_reply_not_a_failure() -> None:
    client, _ = client_answering(httpx2.Response(200, json={**BASE, "status": "pending_ai"}))
    reply = client.grade_practice({})
    assert isinstance(reply, PracticeGradeReply) and reply.status == "pending_ai"


def test_failures_are_stable_codes_and_never_retried() -> None:
    # Red when: a status or error code is retried (paid twice) or surfaces ai-service's body.
    cases: list[tuple[httpx2.Response | Exception, str, str]] = [
        (httpx2.Response(429, json={"code": "quota_hard_cap"}), "quota", "quota_hard_cap"),
        (httpx2.Response(503, json={"code": "grading_disabled"}), "disabled", "grading_disabled"),
        (httpx2.Response(502, json={"code": "llm_unavailable"}), "unavailable", "llm_unavailable"),
        (httpx2.Response(500, text="SECRET answer echo"), "unavailable", "server_error"),
        (httpx2.Response(422, json={"code": "invalid_request"}), "invalid", "invalid_request"),
        (httpx2.Response(200, json={"status": "ok", "extra": 1}), "invalid", "response_schema"),
        (httpx2.ReadTimeout("t"), "unavailable", "timeout"),
        (httpx2.ConnectError("c"), "unavailable", "connection_error"),
    ]
    for answer, failure, reason in cases:
        client, seen = client_answering(answer)
        out = client.grade_practice({})
        assert isinstance(out, NotGraded), answer
        assert (out.failure, out.reason) == (failure, reason)
        assert len(seen) == 1
        assert "SECRET" not in repr(out)


def test_review_question_t79_parses_the_reply_and_posts_once() -> None:
    # T7.9. Red when: the strict contract refuses a reply with the question, rubric and answer, or
    # the path is not /v1/review-question, or a second call is made.
    client, seen = client_answering(
        httpx2.Response(
            200,
            json={
                **BASE,
                "status": "ok",
                "prompt": "Q?",
                "reference_answer": "A.",
                "rubric": "R.",
            },
        )
    )
    reply = client.review_question({"title": "t"})
    assert not isinstance(reply, NotGraded)
    assert (reply.status, reply.prompt, reply.rubric) == ("ok", "Q?", "R.")
    assert len(seen) == 1


def test_review_question_t79_connection_error_is_unavailable() -> None:
    client, _ = client_answering(httpx2.ConnectError("down"))
    reply = client.review_question({})
    assert isinstance(reply, NotGraded) and reply.failure == "unavailable"
