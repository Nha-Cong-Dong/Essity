"""Q13 (05/11): a subject with review history can be deleted; it is then hidden everywhere and its
rows stay. A second user's subject of the same name is never touched."""

import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_subjects_api import create, in_days

from accounts import signed_in
from clock import FROZEN_NOW, spare_day
from core_api.db.models import MemoryState, Subject, User
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import AttemptRepository, ReviewSessionRepository
from v2_rows import make_study_session, make_unit

NAME = "Mạng máy tính QX"


def _with_history(db: Session, user: User, subject_id: str) -> None:
    subject = db.get(Subject, uuid.UUID(subject_id))
    assert subject is not None
    make_study_session(db, user, subject)
    unit = make_unit(db, user, subject, status="canonical", title="Thẻ lịch sử")
    db.add(
        MemoryState(
            user_id=user.id,
            unit_id=unit.id,
            facet="core",
            phase="review",
            step=None,
            stability=3.0,
            difficulty=5.0,
            due=FROZEN_NOW - timedelta(hours=2),
            last_review=FROZEN_NOW - timedelta(days=3),
        )
    )
    question = QuestionRepository(db, user.id).add_idempotent(
        subject.id, level=1, prompt="TCP?", reference_answer="a", run_id=uuid.uuid4()
    )
    review = ReviewSessionRepository(db, user.id).start(spare_day(), FROZEN_NOW)
    attempts = AttemptRepository(db, user.id)
    attempt = attempts.create_draft(review.id, question.id)
    attempts.submit(attempt.id, FROZEN_NOW)
    db.commit()


def _bodies(client: TestClient, headers: dict[str, str], subject_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, path in {
        "today": "/v1/today",
        "stats": "/v1/stats",
        "subjects": "/v1/subjects",
        "vault": "/v1/vault/subjects",
    }.items():
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)
        out[name] = response.text
    for name, path in {
        "graph": f"/v1/subjects/{subject_id}/graph",
        "questions": f"/v1/subjects/{subject_id}/questions",
        "vault_sessions": f"/v1/vault/subjects/{subject_id}/sessions",
    }.items():
        out[name] = client.get(path, headers=headers).status_code
    return out


def test_q13_a_deleted_subject_with_history_is_hidden_everywhere(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, NAME, in_days(user, 30)).json()["id"]
    _with_history(db_session, user, subject_id)
    before = _bodies(client, headers, subject_id)
    assert NAME in before["subjects"]
    assert '"question_id"' in before["today"], before["today"]  # its question is due

    assert client.delete(f"/v1/subjects/{subject_id}", headers=headers).status_code == 204

    after = _bodies(client, headers, subject_id)
    assert '"question_id"' not in after["today"]  # its due question is gone from Hôm nay
    for key in ("today", "stats", "subjects", "vault"):
        assert NAME not in after[key], key
        assert subject_id not in after[key], key
    assert (after["graph"], after["questions"], after["vault_sessions"]) == (404, 404, 404)
    kept = db_session.scalar(
        text("select count(*) from attempt where user_id = :u"), {"u": user.id}
    )
    assert kept == 1


def test_q13_another_users_subject_of_the_same_name_is_untouched(
    client: TestClient, db_session: Session
) -> None:
    alice, alice_headers = signed_in(db_session)
    bob, bob_headers = signed_in(db_session)
    mine = create(client, alice_headers, NAME, in_days(alice, 30)).json()["id"]
    theirs = create(client, bob_headers, NAME, in_days(bob, 30)).json()["id"]
    _with_history(db_session, alice, mine)
    _with_history(db_session, bob, theirs)

    assert client.delete(f"/v1/subjects/{theirs}", headers=alice_headers).status_code == 404
    assert client.delete(f"/v1/subjects/{mine}", headers=alice_headers).status_code == 204

    bobs = _bodies(client, bob_headers, theirs)
    assert NAME in bobs["subjects"] and NAME in bobs["stats"]
    assert (bobs["graph"], bobs["questions"]) == (200, 200)
