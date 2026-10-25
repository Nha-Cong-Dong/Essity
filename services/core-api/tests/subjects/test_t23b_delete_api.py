"""T2.3b: `DELETE /v1/subjects/{id}` and `has_history` in the list (us-01 AC8; plan F2, F3).

The locking under it is tested in `test_t23b_soft_delete.py` and
`review/test_t23b_subject_lock_race.py`; here, what a caller sees.
"""

import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_subjects_api import create, in_days

from accounts import signed_in
from clock import FROZEN_NOW, spare_day
from core_api.db.models import User
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import AttemptRepository, ReviewSessionRepository

DAY = date(2026, 10, 23)


def delete(client: TestClient, headers: dict[str, str], subject_id: str) -> Any:
    return client.delete(f"/v1/subjects/{subject_id}", headers=headers)


def attempt_on(session: Session, user: User, subject_id: str, *, submitted: bool) -> None:
    question = QuestionRepository(session, user.id).add_idempotent(
        uuid.UUID(subject_id), level=1, prompt="TCP?", reference_answer="a", run_id=uuid.uuid4()
    )
    review = ReviewSessionRepository(session, user.id).start(spare_day(), FROZEN_NOW)
    attempts = AttemptRepository(session, user.id)
    attempt = attempts.create_draft(review.id, question.id)
    if submitted:
        attempts.submit(attempt.id, FROZEN_NOW)
    session.flush()


@pytest.fixture
def owned(client: TestClient, db_session: Session) -> tuple[User, dict[str, str], str]:
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng máy tính", in_days(user, 30)).json()["id"]
    return user, headers, subject_id


def test_us01_ac8_delete_answers_204_and_the_subject_leaves_the_list(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    user, headers, subject_id = owned
    kept = create(client, headers, "Hệ điều hành", in_days(user, 40)).json()["id"]
    response = delete(client, headers, subject_id)
    assert (response.status_code, response.content) == (204, b"")
    assert [s["id"] for s in client.get("/v1/subjects", headers=headers).json()] == [kept]


def test_us01_ac8_deleted_at_is_the_request_clock(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    # Red when: the route passes its own `datetime.now` instead of `Now` (R23/R34).
    _, headers, subject_id = owned
    assert delete(client, headers, subject_id).status_code == 204
    stored = db_session.execute(
        text("SELECT deleted_at FROM subject WHERE id = :id"), {"id": subject_id}
    ).scalar_one()
    assert stored == FROZEN_NOW


def test_us01_ac8_deleting_the_last_subject_clears_has_subjects(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    _, headers, subject_id = owned
    assert client.get("/v1/me", headers=headers).json()["has_subjects"] is True
    assert delete(client, headers, subject_id).status_code == 204
    assert client.get("/v1/me", headers=headers).json()["has_subjects"] is False


@pytest.mark.parametrize("submitted", [False, True], ids=["draft", "submitted"])
def test_us01_ac8_a_subject_with_an_attempt_answers_409_subject_has_history(
    client: TestClient,
    db_session: Session,
    owned: tuple[User, dict[str, str], str],
    submitted: bool,
) -> None:
    user, headers, subject_id = owned
    attempt_on(db_session, user, subject_id, submitted=submitted)
    response = delete(client, headers, subject_id)
    assert (response.status_code, response.json()) == (409, {"detail": "subject_has_history"})
    assert [s["id"] for s in client.get("/v1/subjects", headers=headers).json()] == [subject_id]


def test_us01_ac8_list_reports_has_history(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    user, headers, subject_id = owned
    fresh = create(client, headers, "Mới", in_days(user, 40)).json()["id"]
    attempt_on(db_session, user, subject_id, submitted=False)
    listed = {s["id"]: s["has_history"] for s in client.get("/v1/subjects", headers=headers).json()}
    assert listed == {subject_id: True, fresh: False}


def test_us01_ac8_deleting_someone_elses_subject_answers_404_and_changes_nothing(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    _, alice, subject_id = owned
    _, bob = signed_in(db_session)
    response = delete(client, bob, subject_id)
    assert (response.status_code, response.json()) == (404, {"detail": "subject_not_found"})
    assert [s["id"] for s in client.get("/v1/subjects", headers=alice).json()] == [subject_id]


def test_us01_ac8_deleting_twice_answers_404(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    _, headers, subject_id = owned
    assert delete(client, headers, subject_id).status_code == 204
    response = delete(client, headers, subject_id)
    assert (response.status_code, response.json()) == (404, {"detail": "subject_not_found"})


def test_us01_ac8_unknown_subject_is_404_and_malformed_id_is_422(
    client: TestClient, db_session: Session
) -> None:
    _, headers = signed_in(db_session)
    assert delete(client, headers, str(uuid.uuid4())).status_code == 404
    assert delete(client, headers, "not-a-uuid").status_code == 422


def test_us01_ac8_patch_of_a_deleted_subject_answers_404(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    _, headers, subject_id = owned
    assert delete(client, headers, subject_id).status_code == 204
    response = client.patch(f"/v1/subjects/{subject_id}", json={"name": "Mạng"}, headers=headers)
    assert response.status_code == 404


def test_us01_ac8_delete_needs_a_verified_user(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session, verified=False)
    response = delete(client, headers, str(uuid.uuid4()))
    assert (response.status_code, response.json()) == (403, {"detail": "email_not_verified"})


def test_us01_ac8_delete_needs_a_session(client: TestClient) -> None:
    assert client.delete(f"/v1/subjects/{uuid.uuid4()}").status_code == 401
