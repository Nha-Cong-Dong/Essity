"""T2.23, the unit ids web T2.24 needs to call "Không cần ôn phần này" on the current question."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_t223_skip_api import unit_of
from test_t29_review_sessions_api import current, ready, start


# Red when: the current question does not carry the ids of its own units, so the screen cannot
# call the skip.
def test_t223_the_current_question_carries_its_unit_ids(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _ = ready(db_session, 2)
    session = start(client, headers).json()
    question = current(client, headers, session["id"])["question"]
    assert question["unit_ids"] == [str(unit_of(db_session, space, question["id"]))]
    assert all(uuid.UUID(u) for u in question["unit_ids"])
