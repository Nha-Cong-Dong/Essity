"""T2.9: the review session API, before grading (US-04, US-08, PLAN T2.9, plan
`t2.8-t2.9-t2.14-today-session.md`). Submitting grades the answer (T2.13): conftest's stub
grader stands in for ai-service."""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_t28_today_api import Space

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.clients.ai_client import NotGraded
from core_api.db.models import Attempt, Question, ReviewSession
from core_api.repositories.subject import SubjectRepository
from grader_stub import Stub

Headers = dict[str, str]


def start(client: TestClient, headers: Headers, **body: Any) -> Any:
    return client.post("/v1/review-sessions", json=body, headers=headers)


def current(client: TestClient, headers: Headers, session_id: str) -> Any:
    response = client.get(f"/v1/review-sessions/{session_id}/current", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def open_attempt(client: TestClient, headers: Headers, session_id: str) -> Any:
    return client.post(f"/v1/review-sessions/{session_id}/attempts", headers=headers)


def ready(db_session: Session, questions: int = 2) -> tuple[Space, Headers, list[uuid.UUID]]:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    ids = [space.question(subject, f"q{n}")[1].id for n in range(questions)]
    return space, headers, ids


# --- starting -------------------------------------------------------------------------------


def test_t29_start_makes_a_session_with_todays_questions(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _ = ready(db_session, 3)
    response = start(client, headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["total"] == 3 and body["answered"] == 0


# Plan C4. Red when: a second press makes a second session instead of returning the first.
def test_t29_start_again_returns_the_open_session(client: TestClient, db_session: Session) -> None:
    _, headers, _ = ready(db_session)
    first = start(client, headers).json()
    again = start(client, headers)
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]


def test_t29_nothing_to_review(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    Space(db_session, user).subject()
    response = start(client, headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "nothing_to_review"}


# US-03 AC7 (plan C8). Red when: the subject filter is ignored, or another user's subject works.
def test_us03_ac7_a_session_of_one_subject(client: TestClient, db_session: Session) -> None:
    space, headers, _ = ready(db_session, 2)
    other = space.subject("Hệ điều hành")
    space.question(other, "Tiến trình")
    body = start(client, headers, subject_id=str(other)).json()
    assert body["total"] == 1
    _, bob_headers = signed_in(db_session)
    assert start(client, bob_headers, subject_id=str(other)).status_code == 404


# --- the current question -------------------------------------------------------------------


# US-04 AC1. Red when: the reference answer, rubric or level reaches the answer screen.
def test_us04_ac1_current_shows_only_the_question(client: TestClient, db_session: Session) -> None:
    _, headers, ids = ready(db_session, 2)
    session_id = start(client, headers).json()["id"]
    body = current(client, headers, session_id)
    assert body["done"] is False
    assert (body["position"], body["total"]) == (1, 2)
    assert body["question"]["id"] in {str(i) for i in ids}
    assert set(body["question"]) == {"id", "prompt", "subject"}
    assert body["attempt"] is None


# Plan C1 / tech-expert. Red when: a question of a subject deleted after the session started is
# still offered, or still counted.
def test_t29_a_deleted_subjects_question_is_skipped(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _ = ready(db_session, 1)
    gone = space.subject("Xóa")
    space.question(gone, "x")
    session_id = start(client, headers).json()["id"]
    SubjectRepository(db_session, space.user.id).soft_delete(gone, FROZEN_NOW)
    body = current(client, headers, session_id)
    assert body["total"] == 1
    assert body["question"]["subject"]["id"] != str(gone)


# --- drafts and answers ---------------------------------------------------------------------


def test_t29_opening_the_current_question_makes_one_draft(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _ = ready(db_session)
    session_id = start(client, headers).json()["id"]
    first = open_attempt(client, headers, session_id)
    assert first.status_code == 201, first.text
    again = open_attempt(client, headers, session_id)
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert current(client, headers, session_id)["attempt"]["id"] == first.json()["id"]


def test_t29_a_draft_keeps_its_text_and_lines(client: TestClient, db_session: Session) -> None:
    _, headers, _ = ready(db_session)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    text = "Dòng một\nDòng hai\tcó tab"
    saved = client.put(
        f"/v1/attempts/{attempt_id}/draft",
        json={"answer_text": text, "dont_remember": False},
        headers=headers,
    )
    assert saved.status_code == 204, saved.text
    assert current(client, headers, session_id)["attempt"]["answer_text"] == text


def test_t29_control_characters_other_than_lines_are_refused(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _ = ready(db_session)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    response = client.put(
        f"/v1/attempts/{attempt_id}/draft",
        json={"answer_text": "a\x00b", "dont_remember": False},
        headers=headers,
    )
    assert response.status_code == 422
    assert "a\x00b" not in response.text


def submit(
    client: TestClient, headers: Headers, attempt_id: str, text: str, forgot: bool = False
) -> Any:
    return client.post(
        f"/v1/attempts/{attempt_id}/submit",
        json={"answer_text": text, "dont_remember": forgot},
        headers=headers,
    )


# US-04 AC4 at the API. Red when: an empty answer without "Không nhớ" is submitted.
def test_us04_ac4_an_empty_answer_needs_dont_remember(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _ = ready(db_session)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    refused = submit(client, headers, attempt_id, "   ")
    assert refused.status_code == 422
    assert refused.json() == {"detail": "answer_empty"}
    assert submit(client, headers, attempt_id, "", forgot=True).status_code == 200


# Red when: submitting saves the text typed after the last draft save, or moves on wrongly.
def test_t29_submit_saves_the_last_text_and_moves_on(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _ = ready(db_session, 2)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    done = submit(client, headers, attempt_id, "TCP tin cậy")
    assert done.status_code == 200
    assert (done.json()["status"], done.json()["grading"]) == ("submitted", "graded")
    nxt = current(client, headers, session_id)
    assert (nxt["position"], nxt["total"], nxt["attempt"]) == (2, 2, None)


# Plan D14 / PLAN T2.9. Red when: a second submit changes the answer or fails.
def test_t29_double_submit_returns_the_first(client: TestClient, db_session: Session) -> None:
    _, headers, _ = ready(db_session)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    submit(client, headers, attempt_id, "lần một")
    assert submit(client, headers, attempt_id, "lần hai").status_code == 200
    client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers)
    assert submit(client, headers, attempt_id, "sau khi dừng").status_code == 200
    db_session.expire_all()
    stored = db_session.get(Attempt, uuid.UUID(attempt_id))
    assert stored is not None and stored.answer_text == "lần một"


# --- stopping -------------------------------------------------------------------------------


def test_us08_stop_counts_and_closes_once(client: TestClient, db_session: Session) -> None:
    _, headers, _ = ready(db_session, 2)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    submit(client, headers, attempt_id, "x")
    stopped = client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json() == {
        "answered": 1,
        "total": 2,
        "correct": 1,
        "next_day": stopped.json()["next_day"],
    }
    again = client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers)
    assert again.json() == stopped.json()
    assert current(client, headers, session_id) == {"done": True, "ungraded": []}


# D14. Red when: a draft can still change once its session is stopped.
def test_t29_draft_after_stop_is_refused(client: TestClient, db_session: Session) -> None:
    _, headers, _ = ready(db_session)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers)
    response = client.put(
        f"/v1/attempts/{attempt_id}/draft",
        json={"answer_text": "muộn", "dont_remember": False},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "session_ended"}


# --- isolation, clock, logs -----------------------------------------------------------------


# ADR-0001. Red when: B reaches A's session or attempt through any route.
def test_t29_isolated_two_users(client: TestClient, db_session: Session) -> None:
    _, alice, _ = ready(db_session)
    _, bob = signed_in(db_session)
    session_id = start(client, alice).json()["id"]
    attempt_id = open_attempt(client, alice, session_id).json()["id"]
    body = {"answer_text": "của B", "dont_remember": False}
    assert client.get(f"/v1/review-sessions/{session_id}/current", headers=bob).status_code == 404
    assert open_attempt(client, bob, session_id).status_code == 404
    assert client.put(f"/v1/attempts/{attempt_id}/draft", json=body, headers=bob).status_code == 404
    assert (
        client.post(f"/v1/attempts/{attempt_id}/submit", json=body, headers=bob).status_code == 404
    )
    assert client.post(f"/v1/review-sessions/{session_id}/stop", headers=bob).status_code == 404
    assert current(client, alice, session_id)["attempt"]["answer_text"] == ""


def test_t29_learning_day_at_0359_and_0400(
    client: TestClient, db_session: Session, set_now: Callable[[datetime], None]
) -> None:
    _, headers, _ = ready(db_session, 3)
    set_now(datetime(2026, 10, 24, 20, 59, tzinfo=FROZEN_NOW.tzinfo))  # 03:59 on the 25th, HCM
    before = start(client, headers).json()["id"]
    set_now(datetime(2026, 10, 24, 21, 0, tzinfo=FROZEN_NOW.tzinfo))  # 04:00: a new learning day
    after = start(client, headers)
    assert after.status_code == 201
    assert after.json()["id"] != before


# ADR-0013. Red when: the answer text reaches the application log.
def test_t29_answer_text_not_logged(
    client: TestClient, db_session: Session, log_output: Callable[[], str]
) -> None:
    _, headers, _ = ready(db_session)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    secret = "câu-trả-lời-không-được-ghi-log"
    client.put(
        f"/v1/attempts/{attempt_id}/draft",
        json={"answer_text": secret, "dont_remember": False},
        headers=headers,
    )
    submit(client, headers, attempt_id, secret)
    assert secret not in log_output()


# US-03 / DESIGN §6.3: an open session today turns "Bắt đầu" into "Tiếp tục" with "7/14". Red
# when: /v1/today does not report the session, or reports one from an earlier learning day.
def test_t28_today_reports_the_session_in_progress(client: TestClient, db_session: Session) -> None:
    _, headers, _ = ready(db_session, 2)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    submit(client, headers, attempt_id, "x")
    body = client.get("/v1/today", headers=headers).json()
    assert body["state"] == "in_progress"
    assert body["in_progress"] == {"session_id": session_id, "position": 2, "total": 2}
    client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers)
    assert client.get("/v1/today", headers=headers).json()["in_progress"] is None


# Review #21 🟠. Red when: a session whose every question is answered, left open because the tab
# closed before "stop", keeps today's one open slot, so "Bắt đầu" returns the finished session.
def test_t29_a_finished_open_session_does_not_block_a_new_one(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    stub.failure = NotGraded("unavailable", "timeout")  # ungraded, the question is still due
    _, headers, _ = ready(db_session, 1)
    first = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, first).json()["id"]
    submit(client, headers, attempt_id, "x")  # the tab closes here, before stop
    again = start(client, headers)
    assert again.status_code == 201, again.text
    assert again.json()["id"] != first
    assert current(client, headers, first) == {"done": True, "ungraded": [attempt_id]}
    db_session.expire_all()
    closed = db_session.get(ReviewSession, uuid.UUID(first))
    assert closed is not None and closed.ended_at is not None
    assert closed.stop_reason == "completed"


# PLAN T2.9 (23/10b), plan C11. Red when: a subject deleted between reading the session's steps
# and writing the draft leaves an attempt on it, or answers anything but 404 subject_deleted. The
# race is opened by deleting the subject just before open_draft runs.
def test_t29_draft_on_a_subject_deleted_meanwhile_is_404_and_leaves_no_attempt(
    client: TestClient, db_session: Session, monkeypatch: Any
) -> None:
    space, headers, _ = ready(db_session, 1)
    session_id = start(client, headers).json()["id"]
    from core_api.repositories import review as review_repo

    original = review_repo.AttemptRepository.open_draft

    def deleted_first(self: Any, review_session_id: uuid.UUID, question_id: uuid.UUID) -> Any:
        subject_id = db_session.get(Question, question_id).subject_id  # type: ignore[union-attr]
        SubjectRepository(db_session, space.user.id).soft_delete(subject_id, FROZEN_NOW)
        return original(self, review_session_id, question_id)

    monkeypatch.setattr(review_repo.AttemptRepository, "open_draft", deleted_first)
    response = open_attempt(client, headers, session_id)
    assert response.status_code == 404
    assert response.json() == {"detail": "subject_deleted"}
    count = db_session.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.user_id == space.user.id)
    )
    assert count == 0


# T2.13 plan D-4. Red when: an answer ai-service would refuse (> 4000 characters) is stored, so it
# could never be graded and "Chấm lại" would loop.
def test_t213_an_answer_over_4000_characters_is_refused(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _ = ready(db_session)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    for text, code in [("ệ" * 4000, 204), ("ệ" * 4000 + "x", 422)]:
        body = {"answer_text": text, "dont_remember": False}
        response = client.put(f"/v1/attempts/{attempt_id}/draft", json=body, headers=headers)
        assert response.status_code == code


# US-08 AC1, AC2. Red when: the summary counts a forgotten answer as correct, drops the answers
# given before "Dừng tại đây", or names a next day that is not after today.
def test_us08_ac1_stop_summary_counts_correct_and_names_the_next_day(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _ = ready(db_session, 3)
    session_id = start(client, headers).json()["id"]
    for text, forgot in (("đúng", False), ("", True)):
        attempt_id = open_attempt(client, headers, session_id).json()["id"]
        assert submit(client, headers, attempt_id, text, forgot).status_code == 200
    stopped = client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers).json()
    assert (stopped["answered"], stopped["total"], stopped["correct"]) == (2, 3, 1)
    assert stopped["next_day"] is not None
    assert stopped["next_day"] > space.today.isoformat()


def test_us08_ac1_stop_summary_has_no_next_day_without_a_schedule(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _ = ready(db_session, 1)
    session_id = start(client, headers).json()["id"]
    stopped = client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers).json()
    assert stopped == {"answered": 0, "total": 1, "correct": 0, "next_day": None}


# US-08 AC2, PLAN T2.17. Red when: stopping midway loses the answered question, or the
# unanswered one does not come back in the next session.
def test_us08_ac2_stopped_midway_unanswered_returns_to_the_queue(
    client: TestClient, db_session: Session
) -> None:
    _, headers, ids = ready(db_session, 2)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    assert submit(client, headers, attempt_id, "đúng").status_code == 200
    stopped = client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers).json()
    assert (stopped["answered"], stopped["total"]) == (1, 2)
    again = start(client, headers)
    assert again.json()["id"] != session_id
    assert again.json()["total"] == 1
    shown = current(client, headers, again.json()["id"])
    assert shown["question"]["id"] in {str(i) for i in ids}


# ADR-0001, US-08. Red when: B's stop closes A's session.
def test_us08_stop_by_another_user_changes_nothing(client: TestClient, db_session: Session) -> None:
    _, alice, _ = ready(db_session)
    _, bob = signed_in(db_session)
    session_id = start(client, alice).json()["id"]
    assert client.post(f"/v1/review-sessions/{session_id}/stop", headers=bob).status_code == 404
    assert open_attempt(client, alice, session_id).status_code == 201
