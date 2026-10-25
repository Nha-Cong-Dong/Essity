"""T2.9: the review session API, before grading (US-04, US-08, PLAN T2.9, plan
`t2.8-t2.9-t2.14-today-session.md`). Grading is T2.13: a submitted answer is "pending" here."""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_t28_today_api import Space

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.repositories.subject import SubjectRepository

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
    assert done.json() == {"status": "submitted", "grading": "pending"}
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


# --- stopping -------------------------------------------------------------------------------


def test_us08_stop_counts_and_closes_once(client: TestClient, db_session: Session) -> None:
    _, headers, _ = ready(db_session, 2)
    session_id = start(client, headers).json()["id"]
    attempt_id = open_attempt(client, headers, session_id).json()["id"]
    submit(client, headers, attempt_id, "x")
    stopped = client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json() == {"answered": 1, "total": 2}
    again = client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers)
    assert again.json() == {"answered": 1, "total": 2}
    assert current(client, headers, session_id) == {"done": True}


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
