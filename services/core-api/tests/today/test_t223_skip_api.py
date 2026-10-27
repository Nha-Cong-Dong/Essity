"""T2.23, `POST` and `DELETE /v1/units/{id}/skip` (US-04 AC5, US-03 AC8): the replacement for a
skipped question, idempotence, isolation between users, and the session cap on undo. What a skip
does to selection is in test_t223_skip_selection.py, to an open session in
test_t223_skip_session.py."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_t28_today_api import Space
from test_t29_review_sessions_api import Headers, current, ready, start

from accounts import signed_in
from core_api.db.models import KnowledgeUnit, ReviewLog, ReviewSession, ReviewSessionItem
from core_api.repositories.question import QuestionUnitRepository
from core_api.repositories.subject import SubjectRepository


def unit_of(db_session: Session, space: Space, question_id: object) -> uuid.UUID:
    (unit,) = QuestionUnitRepository(db_session, space.user.id).units_of(
        uuid.UUID(str(question_id))
    )
    return unit.id


def skip(
    client: TestClient, headers: Headers, unit: uuid.UUID, session_id: str | None = None
) -> Any:
    return client.post(
        f"/v1/units/{unit}/skip", json={"review_session_id": session_id}, headers=headers
    )


def total_items(db_session: Session, session_id: str) -> int:
    return (
        db_session.scalar(
            select(func.count())
            .select_from(ReviewSessionItem)
            .where(ReviewSessionItem.review_session_id == uuid.UUID(session_id))
        )
        or 0
    )


def first_subject(db_session: Session, space: Space) -> uuid.UUID:
    return SubjectRepository(db_session, space.user.id).list()[0].id


def more_questions(db_session: Session, space: Space, count: int) -> None:
    subject = first_subject(db_session, space)
    for n in range(count):
        space.question(subject, f"thêm {n}")


# US-03 AC8. Red when: skipping the current question leaves the session a question short (no
# replacement), or answers with something other than what the screen shows next.
def test_us03_ac8_skip_in_a_session_brings_a_replacement_and_the_next_question(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    space, headers, _ = ready(db_session, 2)
    more_questions(db_session, space, 2)  # four in all
    monkeypatch.setattr("core_api.domain.today.MAX_QUESTIONS", 3)
    monkeypatch.setattr("core_api.repositories.review.MAX_QUESTIONS", 3)
    session = start(client, headers).json()
    assert session["total"] == 3
    first = current(client, headers, session["id"])["question"]["id"]
    response = skip(client, headers, unit_of(db_session, space, first), session["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == session["id"] and body["next"]["done"] is False
    assert body["next"]["total"] == 3 and body["next"]["question"]["id"] != first
    assert total_items(db_session, session["id"]) == 4  # a replacement went after the last item
    assert db_session.scalar(select(func.count()).select_from(ReviewLog)) == 0


# US-03 AC8. Red when: no question is left to take the place, and the skip errors or invents one.
def test_us03_ac8_without_a_replacement_the_session_ends_neutrally(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _ = ready(db_session, 2)
    session = start(client, headers).json()
    first = current(client, headers, session["id"])["question"]["id"]
    body = skip(client, headers, unit_of(db_session, space, first), session["id"]).json()
    assert body["next"]["total"] == 1 and total_items(db_session, session["id"]) == 2
    second = body["next"]["question"]["id"]
    body = skip(client, headers, unit_of(db_session, space, second), session["id"]).json()
    assert body["next"] == {"done": True, "ungraded": []}  # nothing left: a neutral end


# US-04 AC5. Red when: skipping twice appends a second replacement, or fails.
def test_us04_ac5_skip_twice_adds_one_replacement_only(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    space, headers, _ = ready(db_session, 2)
    more_questions(db_session, space, 3)
    monkeypatch.setattr("core_api.domain.today.MAX_QUESTIONS", 2)
    monkeypatch.setattr("core_api.repositories.review.MAX_QUESTIONS", 2)
    session = start(client, headers).json()
    first = current(client, headers, session["id"])["question"]["id"]
    unit = unit_of(db_session, space, first)
    assert skip(client, headers, unit, session["id"]).status_code == 200
    items = total_items(db_session, session["id"])
    assert items == 3
    again = skip(client, headers, unit, session["id"])
    assert again.status_code == 200 and total_items(db_session, session["id"]) == items


# T2.23 (review 🟠5). Red when: no session id still touches a session, or undo is not idempotent.
def test_t223_skip_without_a_session_only_marks_the_unit(
    client: TestClient, db_session: Session
) -> None:
    space, headers, ids = ready(db_session, 2)
    session = start(client, headers).json()
    unit = unit_of(db_session, space, ids[0])
    response = skip(client, headers, unit)
    assert response.status_code == 200
    assert response.json() == {"session_id": None, "next": None}
    assert db_session.get(KnowledgeUnit, unit).skipped_at is not None  # type: ignore[union-attr]
    assert total_items(db_session, session["id"]) == 2
    assert client.delete(f"/v1/units/{unit}/skip", headers=headers).status_code == 204
    assert client.delete(f"/v1/units/{unit}/skip", headers=headers).status_code == 204
    assert db_session.get(KnowledgeUnit, unit).skipped_at is None  # type: ignore[union-attr]


# T2.23. Red when: a session that ended still gets a replacement.
def test_t223_skip_in_an_ended_session_only_marks_the_unit(
    client: TestClient, db_session: Session
) -> None:
    space, headers, ids = ready(db_session, 2)
    session = start(client, headers).json()
    stopped = client.post(f"/v1/review-sessions/{session['id']}/stop", headers=headers)
    assert stopped.status_code == 200
    response = skip(client, headers, unit_of(db_session, space, ids[0]), session["id"])
    assert response.status_code == 200 and response.json() == {"session_id": None, "next": None}
    assert total_items(db_session, session["id"]) == 2


# US-04 AC5, cách ly. Red when: another user's unit or session is used, the answers differ, or a
# 404 on the session still wrote the skip.
def test_t223_other_users_and_unknown_things_are_404_and_change_nothing(
    client: TestClient, db_session: Session
) -> None:
    space, headers, ids = ready(db_session, 2)
    session = start(client, headers).json()
    unit = unit_of(db_session, space, ids[0])
    bob_user, bob = signed_in(db_session)
    bob_space = Space(db_session, bob_user)
    bob_unit, _ = bob_space.question(bob_space.subject("Của Bob"), "bob")
    for response in (
        skip(client, bob, unit),
        skip(client, bob, uuid.uuid4()),
        client.delete(f"/v1/units/{unit}/skip", headers=bob),
    ):
        assert response.status_code == 404 and response.json() == {"detail": "unit_not_found"}
    assert db_session.get(KnowledgeUnit, unit).skipped_at is None  # type: ignore[union-attr]
    unknown = skip(client, headers, unit, str(uuid.uuid4()))
    assert unknown.status_code == 404 and unknown.json() == {"detail": "session_not_found"}
    mine_of_bob = skip(client, bob, bob_unit, session["id"])  # my session, their unit
    assert mine_of_bob.status_code == 404 and mine_of_bob.json() == {"detail": "session_not_found"}
    assert db_session.get(KnowledgeUnit, unit).skipped_at is None  # type: ignore[union-attr]
    assert db_session.get(KnowledgeUnit, bob_unit).skipped_at is None  # type: ignore[union-attr]


# T2.23 "môn xóa mềm". Red when: a unit of a deleted subject can still be skipped.
def test_t223_a_unit_of_a_deleted_subject_is_404(client: TestClient, db_session: Session) -> None:
    space, headers, ids = ready(db_session, 1)
    unit = unit_of(db_session, space, ids[0])
    subject = first_subject(db_session, space)
    assert client.delete(f"/v1/subjects/{subject}", headers=headers).status_code in (200, 204)
    assert skip(client, headers, unit).status_code == 404


# Plan D5 (review 🟠2). Red when: undoing a skip after a replacement went in leaves the session
# with more than its cap of questions to ask.
def test_us03_ac8_undo_after_a_replacement_keeps_the_session_at_its_cap(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    space, headers, _ = ready(db_session, 2)
    more_questions(db_session, space, 1)
    monkeypatch.setattr("core_api.domain.today.MAX_QUESTIONS", 2)
    monkeypatch.setattr("core_api.repositories.review.MAX_QUESTIONS", 2)
    session = start(client, headers).json()
    assert session["total"] == 2
    first = current(client, headers, session["id"])["question"]["id"]
    unit = unit_of(db_session, space, first)
    body = skip(client, headers, unit, session["id"]).json()
    assert body["next"]["total"] == 2 and total_items(db_session, session["id"]) == 3
    assert client.delete(f"/v1/units/{unit}/skip", headers=headers).status_code == 204
    assert current(client, headers, session["id"])["total"] == 2  # not 3


# T2.23 (review 🟠4). Red when: a session of one subject gets a replacement from another subject,
# or does not remember its subject.
def test_t223_the_replacement_comes_from_the_sessions_subject(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _ = ready(db_session, 2)
    mine = first_subject(db_session, space)
    other = space.subject("Hệ điều hành")
    space.question(other, "Tiến trình")
    session = start(client, headers, subject_id=str(mine)).json()
    stored = db_session.get(ReviewSession, uuid.UUID(session["id"]))
    assert stored is not None and stored.subject_id == mine
    first = current(client, headers, session["id"])["question"]["id"]
    body = skip(client, headers, unit_of(db_session, space, first), session["id"]).json()
    assert body["next"]["total"] == 1 and total_items(db_session, session["id"]) == 2
