"""Timing at a real size (T2.8 plan C9, PM gate #20): `GET /v1/today` under 300 ms with ~500
questions (US-03 AC2, PLAN T2.8), and rebuilding one subject's schedule within 5 s with 3 000
review_log rows (US-01 AC3). Rows go in by bulk insert; the routes run as in production."""

import statistics
import time
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, insert
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import (
    Attempt,
    Exam,
    Grade,
    GradeUnit,
    KnowledgeUnit,
    MemoryState,
    Question,
    QuestionUnit,
    ReviewLog,
    ReviewSession,
    Subject,
    User,
)
from core_api.domain.learning_day import learning_day
from core_api.repositories.review import MemoryStateRepository

pytestmark = pytest.mark.timing

RUN = uuid.uuid4()


def bulk_subject(
    session: Session, user: User, name: str, units: int, scheduled: bool
) -> tuple[uuid.UUID, list[uuid.UUID], list[uuid.UUID]]:
    """A subject with `units` units, one question each; a schedule on each unit if `scheduled`."""
    today = learning_day(FROZEN_NOW, ZoneInfo(user.timezone), user.day_start_hour)
    subject_id = uuid.uuid4()
    session.execute(insert(Subject), [{"id": subject_id, "user_id": user.id, "name": name}])
    session.execute(
        insert(Exam),
        [
            {
                "id": uuid.uuid4(),
                "user_id": user.id,
                "subject_id": subject_id,
                "exam_date": today + timedelta(days=40),
            }
        ],
    )
    unit_ids = [uuid.uuid4() for _ in range(units)]
    question_ids = [uuid.uuid4() for _ in range(units)]
    session.execute(
        insert(KnowledgeUnit),
        [
            {
                "id": u,
                "user_id": user.id,
                "subject_id": subject_id,
                "title": f"u{n}",
                "summary": "s",
                "kind": "concept",
                "status": "active",
                "run_id": RUN,
            }
            for n, u in enumerate(unit_ids)
        ],
    )
    session.execute(
        insert(Question),
        [
            {
                "id": q,
                "user_id": user.id,
                "subject_id": subject_id,
                "level": 1,
                "prompt": f"q{n}?",
                "reference_answer": "a",
                "status": "active",
                "content_hash": f"{subject_id.hex}{n:032d}"[:64],
                "run_id": RUN,
            }
            for n, q in enumerate(question_ids)
        ],
    )
    session.execute(
        insert(QuestionUnit),
        [
            {
                "id": uuid.uuid4(),
                "user_id": user.id,
                "subject_id": subject_id,
                "question_id": q,
                "unit_id": u,
            }
            for q, u in zip(question_ids, unit_ids, strict=True)
        ],
    )
    if scheduled:
        session.execute(
            insert(MemoryState),
            [
                {
                    "id": uuid.uuid4(),
                    "user_id": user.id,
                    "unit_id": u,
                    "facet": "core",
                    "phase": "review",
                    "step": None,
                    "stability": 5.0 + n % 30,
                    "difficulty": 5.0,
                    "due": FROZEN_NOW + timedelta(days=(n % 9) - 4),
                    "last_review": FROZEN_NOW - timedelta(days=10),
                }
                for n, u in enumerate(unit_ids)
            ],
        )
    session.flush()
    return subject_id, unit_ids, question_ids


# US-03 AC2 / T2.8. Red when: the reads go one unit at a time (N+1) or miss an index.
def test_us03_ac2_today_500_questions_under_300ms(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    bulk_subject(db_session, user, "Mạng máy tính", 250, scheduled=True)
    bulk_subject(db_session, user, "Hệ điều hành", 200, scheduled=True)
    bulk_subject(db_session, user, "Cấu trúc dữ liệu", 50, scheduled=False)
    assert client.get("/v1/today", headers=headers).status_code == 200  # warm up
    timings: list[float] = []
    for _ in range(7):
        started = time.perf_counter()
        response = client.get("/v1/today", headers=headers)
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200
    # The fastest of seven: a structural slowness (N+1, a query per unit) slows every run, while
    # this machine being busy with other work (other test runs, builds) slows only some.
    best = min(timings)
    print(
        f"GET /v1/today with 500 questions: best {best * 1000:.0f} ms, "
        f"median {statistics.median(timings) * 1000:.0f} ms"
    )
    assert best < 0.3


# US-01 AC3 at a real size. Red when: rebuilding one subject replays the whole account, or
# the latest-grade query goes row by row.
def test_t26_rebuild_one_subject_real_size_under_5s(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    subject_id, unit_ids, question_ids = bulk_subject(db_session, user, "Mạng", 300, True)
    _, other_units, _ = bulk_subject(db_session, user, "Khác", 50, scheduled=True)
    sessions: list[dict[str, object]] = []
    attempts: list[dict[str, object]] = []
    grades: list[dict[str, object]] = []
    units: list[dict[str, object]] = []
    logs: list[dict[str, object]] = []
    for k in range(10):
        at = FROZEN_NOW - timedelta(days=60 - 5 * k)
        sitting = uuid.uuid4()
        sessions.append(
            {"id": sitting, "user_id": user.id, "learning_day": at.date(), "started_at": at}
        )
        for u, q in zip(unit_ids, question_ids, strict=True):
            attempt, grade = uuid.uuid4(), uuid.uuid4()
            attempts.append(
                {
                    "id": attempt,
                    "user_id": user.id,
                    "review_session_id": sitting,
                    "question_id": q,
                    "status": "submitted",
                    "submitted_at": at,
                }
            )
            grades.append(
                {
                    "id": grade,
                    "user_id": user.id,
                    "attempt_id": attempt,
                    "source": "ai",
                    "overall": "correct",
                }
            )
            units.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": user.id,
                    "grade_id": grade,
                    "unit_id": u,
                    "verdict": "correct",
                }
            )
            logs.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": user.id,
                    "unit_id": u,
                    "facet": "core",
                    "rating": 3,
                    "reviewed_at": at,
                    "grade_id": grade,
                }
            )
    for model, rows in [
        (ReviewSession, sessions),
        (Attempt, attempts),
        (Grade, grades),
        (GradeUnit, units),
        (ReviewLog, logs),
    ]:
        db_session.execute(insert(model), rows)
    db_session.flush()
    states = MemoryStateRepository(db_session, user.id)
    others_before = {u: states.state(u) for u in other_units}

    # The fastest of three (R48): another test run on the same Postgres slows only some.
    timings: list[float] = []
    written = 0
    for _ in range(3):
        started = time.perf_counter()
        written = states.rebuild(subject_id=subject_id)
        timings.append(time.perf_counter() - started)
    elapsed = min(timings)
    print(f"rebuild one subject, 300 units x 10 reviews: {elapsed:.2f} s")

    assert written == 300
    assert elapsed <= 5
    assert {u: states.state(u) for u in other_units} == others_before


def statements_per_request(client: TestClient, session: Session, headers: dict[str, str]) -> int:
    count = 0

    def counted(*_: object) -> None:
        nonlocal count
        count += 1

    connection = session.connection()
    event.listen(connection, "before_cursor_execute", counted)
    try:
        assert client.get("/v1/today", headers=headers).status_code == 200
    finally:
        event.remove(connection, "before_cursor_execute", counted)
    return count


# US-03 AC2, independent of how busy the machine is. Red when: a query runs per unit or per
# question (N+1), so the count grows with the account.
def test_us03_ac2_today_runs_the_same_queries_for_10_or_500_questions(
    client: TestClient, db_session: Session
) -> None:
    small_user, small = signed_in(db_session)
    bulk_subject(db_session, small_user, "Mạng", 10, scheduled=True)
    large_user, large = signed_in(db_session)
    bulk_subject(db_session, large_user, "Mạng", 250, scheduled=True)
    bulk_subject(db_session, large_user, "Hệ điều hành", 250, scheduled=False)
    assert statements_per_request(client, db_session, small) == statements_per_request(
        client, db_session, large
    )
