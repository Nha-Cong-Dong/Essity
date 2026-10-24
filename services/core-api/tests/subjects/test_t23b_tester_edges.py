"""T2.3b, independent tester: edges the plan's table leaves open (us-01 AC8)."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_subjects_api import create, in_days
from test_t23b_delete_api import attempt_on, delete

from accounts import signed_in
from core_api.repositories.question import QuestionRepository


def _count(session: Session, table: str, subject_id: str) -> int:
    return int(
        session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE subject_id = :s"),  # noqa: S608 - fixed names
            {"s": subject_id},
        )
        or 0
    )


def test_us01_ac8_another_subjects_attempt_does_not_block_this_delete(
    client: TestClient, db_session: Session
) -> None:
    # Red when: the history check stops tying the attempt to the subject being deleted (any
    # attempt of the user, or of any subject, then blocks the delete).
    user, headers = signed_in(db_session)
    busy = create(client, headers, "Mạng", in_days(user, 30)).json()["id"]
    idle = create(client, headers, "Hệ điều hành", in_days(user, 40)).json()["id"]
    attempt_on(db_session, user, busy, submitted=False)
    assert delete(client, headers, idle).status_code == 204
    assert delete(client, headers, busy).status_code == 409


def test_us01_ac8_soft_delete_keeps_the_exam_and_the_questions(
    client: TestClient, db_session: Session
) -> None:
    # Red when: DELETE removes the subject's exam or questions instead of only hiding the subject
    # ("exam, questions and units stay but are hidden").
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng", in_days(user, 30)).json()["id"]
    QuestionRepository(db_session, user.id).add_idempotent(
        uuid.UUID(subject_id), level=1, prompt="TCP?", reference_answer="a", run_id=uuid.uuid4()
    )
    db_session.flush()
    before = (_count(db_session, "exam", subject_id), _count(db_session, "question", subject_id))
    assert before == (1, 1)
    assert delete(client, headers, subject_id).status_code == 204
    assert (
        _count(db_session, "exam", subject_id),
        _count(db_session, "question", subject_id),
    ) == before


def test_us01_ac8_a_refused_delete_leaves_the_subject_renamable(
    client: TestClient, db_session: Session
) -> None:
    # Red when: PATCH starts refusing subjects with history, or the 409 path marks the subject.
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng", in_days(user, 30)).json()["id"]
    attempt_on(db_session, user, subject_id, submitted=True)
    assert delete(client, headers, subject_id).status_code == 409
    renamed = client.patch(
        f"/v1/subjects/{subject_id}", json={"name": "Mạng máy tính"}, headers=headers
    )
    assert (renamed.status_code, renamed.json()["name"]) == (200, "Mạng máy tính")
    listed = client.get("/v1/subjects", headers=headers).json()
    assert [(s["name"], s["has_history"]) for s in listed] == [("Mạng máy tính", True)]
