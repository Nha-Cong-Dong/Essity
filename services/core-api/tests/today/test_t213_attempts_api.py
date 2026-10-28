"""T2.13 (US-04, US-05; plan D-7, 🟠3, 🟠4): submitting grades the answer at once; "Chấm lại";
reading an attempt back. The grader is a stub behind the `get_ai_client` dependency."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_t28_today_api import Space

from accounts import signed_in
from core_api.clients.ai_client import NotGraded
from core_api.main import app
from core_api.security.rate_limit import RateLimiterUnavailableError, get_rate_limiter
from grader_stub import Stub

Headers = dict[str, str]


def opened(client: TestClient, db_session: Session) -> tuple[Space, Headers, str, str]:
    """A user with one question, a started session and the draft of its first question."""
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    space.question(space.subject(), "TCP")
    session_id = client.post("/v1/review-sessions", json={}, headers=headers).json()["id"]
    attempt_id = client.post(f"/v1/review-sessions/{session_id}/attempts", headers=headers).json()[
        "id"
    ]
    return space, headers, session_id, attempt_id


def submit(
    client: TestClient,
    headers: Headers,
    attempt_id: str,
    text: str = "TCP tin cậy",
    forgot: bool = False,
) -> Any:
    return client.post(
        f"/v1/attempts/{attempt_id}/submit",
        json={"answer_text": text, "dont_remember": forgot},
        headers=headers,
    )


# US-05 AC2, AC8; T2.13 case 1. Red when: submitting does not grade, or the result lacks the
# reference answer or the sources the grade used.
def test_us05_ac2_submit_grades_and_answers_the_result(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    body = submit(client, headers, attempt_id).json()
    assert (body["status"], body["grading"], body["failure"]) == ("submitted", "graded", None)
    result = body["result"]
    assert result["overall"] == "correct" and result["understanding"] == 3
    assert result["reference_answer"] == "a"
    sent = stub.calls[0]["units"][0]["anchors"][0]  # type: ignore[index]
    assert [s["anchor_id"] for s in result["sources"]] == [sent["anchor_id"]]
    assert result["sources"][0]["quote_text"] == sent["quote_text"]
    assert result["practice"] is False
    assert [u["verdict"] for u in result["units"]] == ["correct"]


# T2.13 case 2, PLAN T2.13 23/10 (R03). Red when: a failed grading loses the answer or cannot be
# graded again later.
def test_t213_a_failed_grading_keeps_the_answer_and_chấm_lại_grades_it(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    # A failure that cannot clear; one that may goes to the queue (test_t419_async_grading).
    stub.failure = NotGraded("invalid", "grade_invalid")
    body = submit(client, headers, attempt_id).json()
    assert (body["status"], body["grading"], body["failure"], body["result"]) == (
        "submitted",
        "failed",
        "invalid",
        None,
    )
    stub.failure = None
    again = client.post(f"/v1/attempts/{attempt_id}/regrade", headers=headers).json()
    assert again["grading"] == "graded" and again["result"]["overall"] == "correct"


# T4.19 (US-05). Red when: a grading the AI could not take is lost or shown as failed instead of
# waiting, or "Chấm lại" pays for it a second time.
def test_t419_an_unavailable_ai_queues_the_grading_and_the_screen_waits(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    stub.failure = NotGraded("unavailable", "timeout")
    body = submit(client, headers, attempt_id).json()
    assert (body["status"], body["grading"], body["failure"], body["result"]) == (
        "submitted",
        "in_progress",
        None,
        None,
    )
    calls = len(stub.calls)
    stub.failure = None
    for again in (
        client.post(f"/v1/attempts/{attempt_id}/regrade", headers=headers),
        client.get(f"/v1/attempts/{attempt_id}", headers=headers),
    ):
        assert again.json()["grading"] == "in_progress"
    assert len(stub.calls) == calls  # the queued request is not asked a second time


# Plan 🟠3, US-04 AC1. Red when: reading a draft gives away the reference answer or the sources.
def test_t213_reading_a_draft_gives_nothing_away(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    response = client.get(f"/v1/attempts/{attempt_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft" and body["result"] is None
    assert "reference_answer" not in response.text and "quote_text" not in response.text


def test_t213_reading_a_graded_attempt_back(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    submit(client, headers, attempt_id, "Câu của tôi")
    body = client.get(f"/v1/attempts/{attempt_id}", headers=headers).json()
    assert (body["status"], body["grading"], body["answer_text"]) == (
        "submitted",
        "graded",
        "Câu của tôi",
    )
    assert body["submitted_at"] is not None and body["question"]["prompt"] == "TCP?"
    assert body["result"]["overall"] == "correct"
    assert len(stub.calls) == 1  # reading never grades


def test_t213_chấm_lại_on_a_draft_is_409(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    response = client.post(f"/v1/attempts/{attempt_id}/regrade", headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "attempt_not_submitted"}


# US-04 AC2. Red when: "Không nhớ" calls the AI, or its result lacks the answer and the sources.
def test_us04_ac2_dont_remember_shows_the_answer_and_every_source(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    body = submit(client, headers, attempt_id, "", forgot=True).json()
    assert stub.calls == []
    result = body["result"]
    assert (result["overall"], result["understanding"]) == ("forgot", None)
    assert result["reference_answer"] == "a" and len(result["sources"]) == 1


# Plan 🟠4. Red when: a rate limit or a Redis outage stops the answer from being submitted.
def test_t213_limiter_down_still_submits_without_calling_the_ai(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    class Down:
        def enforce(self, *_: object) -> None:
            raise RateLimiterUnavailableError

    app.dependency_overrides[get_rate_limiter] = lambda: Down()
    try:
        _, headers, _, attempt_id = opened(client, db_session)
        body = submit(client, headers, attempt_id).json()
    finally:
        app.dependency_overrides.pop(get_rate_limiter, None)
    assert (body["status"], body["grading"], body["failure"]) == (
        "submitted",
        "failed",
        "unavailable",
    )
    assert stub.calls == []


class Down:
    """A rate limiter whose Redis is down: every check fails closed."""

    def enforce(self, *_: object) -> None:
        raise RateLimiterUnavailableError


# Plan 🟠4 (review 🟡5). Red when: the limit is checked before "Không nhớ" or an existing grade,
# which never call the AI, so a Redis outage turns them into failures.
def test_t213_limiter_down_still_grades_dont_remember_and_returns_a_grade(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, _, forgot_id = opened(client, db_session)
    _, other, _, graded_id = opened(client, db_session)
    assert submit(client, other, graded_id).json()["grading"] == "graded"
    calls = len(stub.calls)
    app.dependency_overrides[get_rate_limiter] = lambda: Down()
    try:
        forgot = submit(client, headers, forgot_id, "", forgot=True).json()
        again = client.post(f"/v1/attempts/{graded_id}/regrade", headers=other).json()
    finally:
        app.dependency_overrides.pop(get_rate_limiter, None)
    assert (forgot["grading"], forgot["result"]["overall"]) == ("graded", "forgot")
    assert (again["grading"], again["result"]["overall"]) == ("graded", "correct")
    assert len(stub.calls) == calls


# Plan D-7. Red when: an answer that failed to grade is lost from the session's view (no way back
# to "Chấm lại"), or "Không nhớ" is listed as ungraded.
def test_t213_current_lists_answers_left_ungraded(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, session_id, attempt_id = opened(client, db_session)
    stub.failure = NotGraded("invalid", "grade_invalid")
    submit(client, headers, attempt_id)
    done = client.get(f"/v1/review-sessions/{session_id}/current", headers=headers).json()
    assert done["done"] is True and done["ungraded"] == [attempt_id]
    stub.failure = None
    client.post(f"/v1/attempts/{attempt_id}/regrade", headers=headers)
    assert (
        client.get(f"/v1/review-sessions/{session_id}/current", headers=headers).json()["ungraded"]
        == []
    )


# ADR-0001. Red when: B reads or grades A's attempt, or the AI is paid for B's request.
def test_t213_isolated_two_users(client: TestClient, db_session: Session, stub: Stub) -> None:
    _, alice, _, attempt_id = opened(client, db_session)
    submit(client, alice, attempt_id)
    calls = len(stub.calls)
    _, bob = signed_in(db_session)
    body = {"answer_text": "của B", "dont_remember": False}
    assert client.get(f"/v1/attempts/{attempt_id}", headers=bob).status_code == 404
    assert client.post(f"/v1/attempts/{attempt_id}/regrade", headers=bob).status_code == 404
    assert (
        client.post(f"/v1/attempts/{attempt_id}/submit", json=body, headers=bob).status_code == 404
    )
    assert len(stub.calls) == calls


# R41 layer 2 at the route (test environment): a fake grade is stored and shown as practice.
def test_t213_a_fake_grade_is_shown_as_practice(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    stub.provider = "fake"
    _, headers, _, attempt_id = opened(client, db_session)
    assert submit(client, headers, attempt_id).json()["result"]["practice"] is True
