"""T2.18, the ids web T2.19 needs to call "Chấm sai" and "Bỏ câu này"."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t213_attempts_api import opened, submit
from test_t218_override_api import grade_id_of

from core_api.db.models import Question


# Red when: the result does not carry the grade's id, or the attempt's question does not carry
# its own, so the override and the drop cannot be called from the screen.
def test_t218_the_attempt_view_exposes_grade_id_and_question_id(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    submitted = submit(client, headers, attempt_id).json()
    viewed = client.get(f"/v1/attempts/{attempt_id}", headers=headers).json()
    grade = grade_id_of(db_session, attempt_id)
    question = db_session.scalars(select(Question)).one()
    for body in (submitted, viewed):
        assert body["result"]["grade_id"] == grade
        assert body["question"]["id"] == str(question.id)
