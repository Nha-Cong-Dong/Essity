"""US-01 AC3 (T2.6): changing a subject's exam date recomputes its schedule within 5 seconds. A
later date needs a replay of review_log, since the exam cap only ever pulls due dates in."""

import time
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.domain.scheduling.rating import ReviewRating, Verdict
from core_api.domain.scheduling.replay import schedule_review
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    AttemptRepository,
    GradeRepository,
    MemoryStateRepository,
    ReviewLogRepository,
    ReviewSessionRepository,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository

RUN = uuid.uuid4()


def remembered_units(
    session: Session,
    user_id: uuid.UUID,
    subject_id: uuid.UUID,
    exam: date,
    units: int,
    tz_name: str,
    day_start_hour: int,
) -> list[uuid.UUID]:
    """Units answered right three times, a week apart, ending a day before FROZEN_NOW."""

    ids: list[uuid.UUID] = []
    for n in range(units):
        unit = KnowledgeUnitRepository(session, user_id).create(
            subject_id, title=f"u{n}", summary="s", kind="concept", run_id=RUN
        )
        question = QuestionRepository(session, user_id).add_idempotent(
            subject_id, level=1, prompt=f"q{n}?", reference_answer="a", run_id=RUN
        )
        QuestionUnitRepository(session, user_id).link(question.id, unit.id)
        state = None
        for k in range(3):
            at = FROZEN_NOW - timedelta(days=15 - 7 * k)
            sitting = ReviewSessionRepository(session, user_id).start(at.date(), at)
            attempts = AttemptRepository(session, user_id)
            attempt = attempts.create_draft(sitting.id, question.id)
            attempts.submit(attempt.id, at)
            grade = GradeRepository(session, user_id).add_with_units(
                attempt.id,
                source="ai",
                overall=Verdict.CORRECT,
                understanding=None,
                units={unit.id: Verdict.CORRECT},
                run_id=RUN,
            )
            ReviewSessionRepository(session, user_id).end(sitting.id, at, reason="completed")
            ReviewLogRepository(session, user_id).append(
                unit.id, rating=ReviewRating.GOOD, reviewed_at=at, grade_id=grade.id
            )
            state = schedule_review(
                state,
                ReviewRating.GOOD,
                at,
                exam_day=exam,
                tz=ZoneInfo(tz_name),
                day_start_hour=day_start_hour,
            )
        assert state is not None
        MemoryStateRepository(session, user_id).upsert(unit.id, "core", state)
        ids.append(unit.id)
    session.flush()
    return ids


# Red when: PATCH changes the exam date but leaves memory_state capped at the old date.
def test_us01_ac3_a_later_exam_date_moves_the_schedule_out(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    near = FROZEN_NOW.date() + timedelta(days=3)
    subject, _ = SubjectRepository(db_session, user.id).create_with_exam("Mạng", near)
    units = remembered_units(
        db_session, user.id, subject.id, near, 2, user.timezone, user.day_start_hour
    )
    states = MemoryStateRepository(db_session, user.id)
    before = {u: states.state(u) for u in units}

    later = (near + timedelta(days=60)).isoformat()
    started = time.monotonic()
    response = client.patch(
        f"/v1/subjects/{subject.id}", json={"exam_date": later}, headers=headers
    )
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed <= 5
    db_session.expire_all()
    for unit_id in units:
        after = states.state(unit_id)
        assert after is not None and before[unit_id] is not None
        assert after.due > before[unit_id].due  # type: ignore[union-attr]


# Red when: a rename alone replays the history (needless work on every PATCH).
def test_us01_ac3_a_rename_leaves_the_schedule_alone(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    exam = FROZEN_NOW.date() + timedelta(days=3)
    subject, _ = SubjectRepository(db_session, user.id).create_with_exam("Mạng", exam)
    (unit,) = remembered_units(
        db_session, user.id, subject.id, exam, 1, user.timezone, user.day_start_hour
    )
    states = MemoryStateRepository(db_session, user.id)
    # A cache that differs from its replay: only a rebuild would change it back.
    marked = states.state(unit)
    assert marked is not None
    states.upsert(
        unit,
        "core",
        replace(marked, due=datetime(2030, 1, 1, tzinfo=UTC)),
    )
    db_session.flush()
    response = client.patch(f"/v1/subjects/{subject.id}", json={"name": "Mạng 2"}, headers=headers)
    assert response.status_code == 200
    db_session.expire_all()
    assert states.state(unit).due == datetime(2030, 1, 1, tzinfo=UTC)  # type: ignore[union-attr]
