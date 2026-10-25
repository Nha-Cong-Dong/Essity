"""T2.13: core-api's call to ai-service's POST /v1/grade and its retry table (plan, "Sửa sau phản
biện" 🟠2, 🟡7). ai-service is a MockTransport: no network, every answer scripted."""

import uuid
from collections.abc import Callable, Iterator

import httpx2
import pytest

from core_api.clients.ai_client import AiServiceClient, Graded, NotGraded

PAYLOAD = {"user_id": str(uuid.uuid4())}
UNIT = uuid.uuid4()
OK = {
    "provider": "fake",
    "model": "fake-grader-v1",
    "prompt_version": "v1",
    "run_id": str(uuid.uuid4()),
    "llm_call_id": str(uuid.uuid4()),
    "overall": "correct",
    "understanding": 3,
    "missing": [],
    "units": [{"unit_id": str(UNIT), "verdict": "correct"}],
    "anchors_used": [str(uuid.uuid4())],
}

Answer = httpx2.Response | Exception


def client_answering(*answers: Answer) -> tuple[AiServiceClient, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []
    script: Iterator[Answer] = iter(answers)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        answer = next(script)
        if isinstance(answer, Exception):
            raise answer
        return answer

    http = httpx2.Client(
        base_url="http://ai", timeout=10.0, transport=httpx2.MockTransport(handler)
    )
    return AiServiceClient(http), seen


def code(status: int, value: str) -> httpx2.Response:
    return httpx2.Response(status, json={"code": value})


def test_t213_a_graded_answer() -> None:
    client, seen = client_answering(httpx2.Response(200, json=OK))
    outcome = client.grade(PAYLOAD)
    assert isinstance(outcome, Graded)
    assert outcome.response.overall == "correct"
    assert outcome.response.units[0].unit_id == UNIT
    assert seen[0].url.path == "/v1/grade"


TIMEOUT = httpx2.ReadTimeout("slow")
REFUSED = httpx2.ConnectError("down")
REDIRECTS = httpx2.TooManyRedirects("loop")


# Plan 🟠2: every row of the retry table, with the number of calls and what the user is told.
# Red when: a 5xx without a known code is not retried, or a refusal is retried (it costs money).
@pytest.mark.parametrize(
    ("answers", "calls", "failure"),
    [
        ([code(502, "llm_unavailable"), code(502, "llm_unavailable")], 2, "unavailable"),
        ([TIMEOUT, TIMEOUT], 2, "unavailable"),
        ([REFUSED, REFUSED], 2, "unavailable"),
        ([REDIRECTS, REDIRECTS], 2, "unavailable"),
        ([httpx2.Response(500, text="Internal Server Error")] * 2, 2, "unavailable"),
        ([code(503, "something_new")] * 2, 2, "unavailable"),
        ([httpx2.Response(504, text="<html>gateway</html>")] * 2, 2, "unavailable"),
        ([code(502, "grade_invalid")], 1, "invalid"),
        ([code(413, "request_too_large")], 1, "invalid"),
        ([code(422, "invalid_request")], 1, "invalid"),
        ([code(503, "grading_disabled")], 1, "disabled"),
        ([code(503, "audit_unavailable")], 1, "unavailable"),
        ([httpx2.Response(401, json={"detail": "x"})], 1, "unavailable"),
        ([httpx2.Response(200, json={**OK, "overall": "brilliant"})], 1, "invalid"),
        ([httpx2.Response(200, text="not json")], 1, "invalid"),
    ],
)
def test_t213_retry_table(answers: list[Answer], calls: int, failure: str) -> None:
    client, seen = client_answering(*answers)
    outcome = client.grade(PAYLOAD)
    assert isinstance(outcome, NotGraded)
    assert (len(seen), outcome.failure) == (calls, failure)


# T2.13 "Xong khi": an error that clears on retry is graded. Red when: 5xx is not retried.
def test_t213_500_then_ok_retries_once() -> None:
    client, seen = client_answering(
        httpx2.Response(500, text="oops"), httpx2.Response(200, json=OK)
    )
    assert isinstance(client.grade(PAYLOAD), Graded)
    assert len(seen) == 2


# Plan 🟡7: the AI leg has 20 s in all. Red when: the retry ignores how little time is left.
def test_t213_no_retry_when_too_little_time_is_left() -> None:
    clock = iter([0.0, 18.0]).__next__
    client, seen = client_answering(code(502, "llm_unavailable"), httpx2.Response(200, json=OK))
    outcome = client.grade(PAYLOAD, clock=clock)
    assert isinstance(outcome, NotGraded) and outcome.failure == "unavailable"
    assert len(seen) == 1


def test_t213_retry_waits_only_for_the_time_left() -> None:
    times: Callable[[], float] = iter([0.0, 14.0]).__next__
    client, seen = client_answering(TIMEOUT, httpx2.Response(200, json=OK))
    assert isinstance(client.grade(PAYLOAD, clock=times), Graded)
    assert seen[1].extensions["timeout"]["read"] == pytest.approx(6.0)


# ADR-0013. Red when: ai-service's error body (which may echo the answer) reaches the log.
def test_t213_error_bodies_are_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    secret = "câu-trả-lời-không-được-ghi-log"
    body = {"code": "invalid_request", "errors": [{"input": secret}]}
    client, _ = client_answering(httpx2.Response(422, json=body))
    with caplog.at_level("DEBUG"):
        client.grade(PAYLOAD)
    assert secret not in caplog.text
