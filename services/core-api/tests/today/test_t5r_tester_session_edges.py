"""T5.R tester edges: a review session started through the API holds level-1 questions only,
whatever level-2/3 questions sit beside them (on a due unit, on a new unit, on no unit), and a
subject whose questions are all above level 1 has nothing to review."""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t5r_level1_only import add_higher
from test_t28_today_api import Space

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import Question, ReviewSessionItem


def session_levels(db_session: Session, session_id: str) -> list[int]:
    return list(
        db_session.scalars(
            select(Question.level)
            .join(ReviewSessionItem, ReviewSessionItem.question_id == Question.id)
            .where(ReviewSessionItem.review_session_id == uuid.UUID(session_id))
        )
    )


# Red when: POST /v1/review-sessions puts a level-2/3 question in the session (due unit, new unit
# or a question linked to no unit), or drops a level-1 question because an older higher one exists.
def test_t5r_a_started_session_holds_level_1_questions_only(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    due_unit, _ = space.question(subject, "TCP")
    space.scheduled(due_unit, due_in_days=-1)
    new_unit, _ = space.question(subject, "UDP")  # never asked: new
    add_higher(space, subject, 2, "Áp dụng TCP?", due_unit)
    add_higher(space, subject, 3, "Nối TCP và UDP?", due_unit, new_unit)
    add_higher(space, subject, 2, "Áp dụng UDP?", new_unit)
    add_higher(space, subject, 2, "Câu mức 2 không gắn ý nào?")  # linked to no unit
    # Truly older than the level-1 ones: created_at is the transaction's now() for every row, so
    # without this the "first question of the unit" falls back to the random uuid order.
    for q in db_session.scalars(
        select(Question).where(Question.user_id == user.id, Question.level > 1)
    ):
        q.created_at = FROZEN_NOW - timedelta(days=30)
    db_session.flush()

    started = client.post("/v1/review-sessions", json={}, headers=headers)
    assert started.status_code == 201, started.text
    body = started.json()
    assert body["total"] == 2
    assert session_levels(db_session, body["id"]) == [1, 1]


# Red when: a subject with only level-2/3 questions (linked to units, some due) can start a
# session instead of answering nothing_to_review.
def test_t5r_only_higher_questions_means_nothing_to_review(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    unit, _ = space.question(subject, "TCP")
    space.scheduled(unit, due_in_days=-1)
    for q in db_session.query(Question).filter(Question.prompt == "TCP?"):
        q.status = "retired"  # the unit keeps only its higher questions
    add_higher(space, subject, 2, "Áp dụng TCP?", unit)
    add_higher(space, subject, 3, "Nối TCP?", unit)

    response = client.post(
        "/v1/review-sessions", json={"subject_id": str(subject)}, headers=headers
    )
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "nothing_to_review"}
