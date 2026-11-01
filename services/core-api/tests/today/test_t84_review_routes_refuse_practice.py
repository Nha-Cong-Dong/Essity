"""T8.4 (US-16 AC11; plan review O1/O2): a practice attempt (no review session) is invisible to
every review route. Red when: a review route grades it as a card (writing review_log), reads it,
submits it, or overrides its grade."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_t28_today_api import Space

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import Attempt, Grade, ReviewLog
from core_api.domain.scheduling.rating import Verdict
from core_api.repositories.practice_attempt import PracticeAttemptRepository
from core_api.repositories.review import GradeRepository
from grader_stub import Stub

UNIT: dict[uuid.UUID, uuid.UUID] = {}


def practice_attempt(
    db_session: Session, submitted: bool = True
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """(user id, attempt id, headers); the question's one unit is `UNIT[attempt id]`."""
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit_id, question = space.question(space.subject(), "TCP")
    repo = PracticeAttemptRepository(db_session, user.id)
    attempt, _ = repo.open_draft(question.id, FROZEN_NOW)
    if submitted:
        repo.submit(attempt.id, FROZEN_NOW, hidden_ms=0, reference_seconds=60.0, answer_text="x")
    db_session.flush()
    UNIT[attempt.id] = unit_id
    return user.id, attempt.id, headers


def review_log_rows(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(ReviewLog)) or 0


def test_read_submit_regrade_all_404_for_a_practice_attempt(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, attempt_id, headers = practice_attempt(db_session)
    before = review_log_rows(db_session)
    assert client.get(f"/v1/attempts/{attempt_id}", headers=headers).status_code == 404
    assert client.post(f"/v1/attempts/{attempt_id}/regrade", headers=headers).status_code == 404
    submit = client.post(
        f"/v1/attempts/{attempt_id}/submit",
        json={"answer_text": "x", "dont_remember": False},
        headers=headers,
    )
    assert submit.status_code == 404
    assert stub.calls == []  # no AI turn was spent
    assert review_log_rows(db_session) == before
    assert db_session.scalar(select(func.count()).select_from(Grade)) == 0


def test_draft_practice_attempt_is_also_404(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, attempt_id, headers = practice_attempt(db_session, submitted=False)
    response = client.post(
        f"/v1/attempts/{attempt_id}/submit",
        json={"answer_text": "x", "dont_remember": False},
        headers=headers,
    )
    assert response.status_code == 404
    attempt = db_session.get(Attempt, attempt_id)
    assert attempt is not None and attempt.status == "draft"


def test_review_override_route_404_for_a_practice_grade(
    client: TestClient, db_session: Session
) -> None:
    user_id, attempt_id, headers = practice_attempt(db_session)
    grade = GradeRepository(db_session, user_id).add_with_units(
        attempt_id,
        source="ai",
        overall=Verdict.CORRECT,
        understanding=None,
        units={UNIT[attempt_id]: Verdict.CORRECT},
        run_id=None,
    )
    db_session.flush()
    before = review_log_rows(db_session)
    response = client.post(
        f"/v1/grades/{grade.id}/override", json={"verdict": "incorrect"}, headers=headers
    )
    assert response.status_code == 404
    assert review_log_rows(db_session) == before
    assert GradeRepository(db_session, user_id).latest_for_attempt(attempt_id) == grade


def test_other_user_gets_404_too(client: TestClient, db_session: Session) -> None:
    _, attempt_id, _ = practice_attempt(db_session)
    _, bob_headers = signed_in(db_session)
    assert client.get(f"/v1/attempts/{attempt_id}", headers=bob_headers).status_code == 404
