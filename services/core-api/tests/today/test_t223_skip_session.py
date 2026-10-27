"""T2.23, what a skipped unit does to a session already open (US-04 AC5, US-03 AC8): its questions
stop being asked and leave the total, a draft is kept but cannot be saved or submitted (409), and
the session never holds more than `MAX_QUESTIONS` (plan D5, review O/🟠2-3). Selection is in
test_t223_skip_selection.py, the routes in test_t223_skip_api.py."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_t28_today_api import Space
from test_t29_review_sessions_api import current, open_attempt, ready, start

from clock import FROZEN_NOW
from core_api.db.models import Attempt, ReviewLog
from core_api.repositories.review import (
    ReviewSessionItemRepository,
    ReviewSessionRepository,
    session_counts,
)
from core_api.repositories.unit import KnowledgeUnitRepository


# US-04 AC5. Red when: a question of a skipped unit is still asked, or still counts in the total.
def test_us04_ac5_a_skipped_unit_leaves_the_open_session(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _ = ready(db_session, 3)
    session_id = start(client, headers).json()["id"]
    first = current(client, headers, session_id)["question"]["id"]
    unit = _unit_of(db_session, space, first)
    assert KnowledgeUnitRepository(db_session, space.user.id).skip(unit, FROZEN_NOW)
    db_session.flush()
    now = current(client, headers, session_id)
    assert now["question"]["id"] != first and now["total"] == 2
    assert db_session.scalar(select(func.count()).select_from(ReviewLog)) == 0  # no history


# US-04 AC5 (review 🟠3). Red when: a draft of a skipped unit's question is still saved or
# submitted, so it would be graded and written to review_log.
def test_us04_ac5_a_draft_of_a_skipped_question_is_kept_but_cannot_be_submitted(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _ = ready(db_session, 2)
    session_id = start(client, headers).json()["id"]
    first = current(client, headers, session_id)["question"]["id"]
    attempt = open_attempt(client, headers, session_id).json()["id"]
    KnowledgeUnitRepository(db_session, space.user.id).skip(
        _unit_of(db_session, space, first), FROZEN_NOW
    )
    db_session.flush()
    saved = client.put(
        f"/v1/attempts/{attempt}/draft",
        json={"answer_text": "x", "dont_remember": False},
        headers=headers,
    )
    assert saved.status_code == 409 and saved.json() == {"detail": "question_not_askable"}
    sent = client.post(
        f"/v1/attempts/{attempt}/submit",
        json={"answer_text": "x", "dont_remember": False},
        headers=headers,
    )
    assert sent.status_code == 409 and sent.json() == {"detail": "question_not_askable"}
    assert db_session.scalar(select(func.count()).select_from(ReviewLog)) == 0
    assert db_session.scalars(select(Attempt.status)).all() == ["draft"]  # kept, not counted
    assert current(client, headers, session_id)["total"] == 1


# US-03 AC8, plan D5. Red when: a session with more items than the cap (a replacement added, then
# the skip undone) has more than the cap of questions that can be asked, answered ones included.
def test_us03_ac8_the_session_never_passes_its_cap(
    db_session: Session, two_users: tuple[object, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _ = two_users
    space = Space(db_session, user)  # type: ignore[arg-type]
    subject = space.subject()
    questions = [space.question(subject, f"q{n}")[1].id for n in range(4)]
    monkeypatch.setattr("core_api.repositories.review.MAX_QUESTIONS", 3)
    session = ReviewSessionRepository(db_session, user.id).start(space.today, FROZEN_NOW)  # type: ignore[attr-defined]
    items = ReviewSessionItemRepository(db_session, user.id)  # type: ignore[attr-defined]
    items.add_all(session.id, questions)
    steps = items.progress(session.id)
    assert [s.askable for s in steps] == [True, True, True, False]  # the last one is hidden
    assert session_counts(steps) == (0, 3)
    attempt = Attempt(
        user_id=user.id,  # type: ignore[attr-defined]
        review_session_id=session.id,
        question_id=questions[3],
        status="submitted",
        submitted_at=FROZEN_NOW,
    )
    db_session.add(attempt)
    db_session.flush()  # an answered question always counts, so one place fewer for the rest
    steps = items.progress(session.id)
    assert session_counts(steps) == (1, 3)
    assert [s.askable for s in steps][:3] == [True, True, False]


def _unit_of(db_session: Session, space: Space, question_id: object) -> uuid.UUID:
    from core_api.repositories.question import QuestionUnitRepository

    (unit,) = QuestionUnitRepository(db_session, space.user.id).units_of(
        uuid.UUID(str(question_id))
    )
    return unit.id


# US-04 AC5 (review T1-Y3). Red when: a draft is opened for the question of a unit skipped after
# the steps were read, so the session holds an attempt that can never be saved.
def test_us04_ac5_no_draft_is_opened_for_a_skipped_question(
    client: TestClient, db_session: Session
) -> None:
    from core_api.repositories.review import AttemptRepository, QuestionNotAskableError

    space, headers, _ = ready(db_session, 2)
    session_id = start(client, headers).json()["id"]
    first = current(client, headers, session_id)["question"]["id"]
    KnowledgeUnitRepository(db_session, space.user.id).skip(
        _unit_of(db_session, space, first), FROZEN_NOW
    )
    db_session.flush()
    with pytest.raises(QuestionNotAskableError):
        AttemptRepository(db_session, space.user.id).open_draft(
            uuid.UUID(session_id), uuid.UUID(first)
        )
    assert db_session.scalars(select(Attempt.status)).all() == []
