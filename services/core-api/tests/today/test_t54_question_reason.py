"""T5.4 (US-07 AC1, AC2): every question of a session carries its reason."""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_t28_today_api import Space
from test_t29_review_sessions_api import current, start

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, MemoryState, Phase
from core_api.repositories.review import MemoryStateRepository


def _stale(db_session: Session, space: Space, unit_id: uuid.UUID, days_ago: int) -> MemoryState:
    state = MemoryState(
        phase=Phase.REVIEW,
        step=None,
        stability=10.0,
        difficulty=5.0,
        due=FROZEN_NOW - timedelta(hours=1),
        last_review=FROZEN_NOW - timedelta(days=days_ago),
    )
    MemoryStateRepository(db_session, space.user.id).upsert(unit_id, "core", state)
    db_session.flush()
    return state


# US-07 AC1. Red when: a never-reviewed question comes without a reason.
def test_us07_ac1_a_new_question_has_a_new_reason(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    space.question(space.subject(), "TCP")
    session = start(client, headers).json()
    reason = current(client, headers, session["id"])["question"]["reason"]
    assert reason == {"kind": "new", "retrievability": None, "days_since_last": None}


# US-07 AC1, AC2. Red when: the reason differs from the memory state and its days.
def test_us07_ac2_a_reviewed_question_cites_its_schedule(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit_id, _ = space.question(space.subject(), "TCP")
    state = _stale(db_session, space, unit_id, 6)
    session = start(client, headers).json()
    reason = current(client, headers, session["id"])["question"]["reason"]
    assert reason["kind"] == "review"
    assert reason["days_since_last"] == 6
    assert reason["retrievability"] == FsrsScheduler().retrievability(state, FROZEN_NOW)
