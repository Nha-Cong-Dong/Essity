"""T2.13 edges found by mutating the code (tester, 26/10): each test names the change in
`src/` that turns it red. The grader is the stub of tests/today/conftest.py."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session
from test_t213_attempts_api import opened, submit

from clock import FROZEN_NOW, future_exam
from core_api.api import attempts as attempts_api
from core_api.api.review_sessions import AnswerIn
from core_api.clients.ai_client import NotGraded
from core_api.clients.redis import get_redis
from core_api.db.models import Attempt, User
from core_api.main import app
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import (
    GRADING_LOCK_NAMESPACE,
    AttemptRepository,
    ReviewSessionItemRepository,
    ReviewSessionRepository,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.user import UserRepository
from core_api.security.rate_limit import RateLimiter, get_rate_limiter
from grader_stub import Stub


# PLAN T2.15 / attempts.submit_attempt. Red when: the check `not body.answer_text.strip()` is
# dropped, so an empty "Gửi" is submitted and paid for as an AI grading.
def test_t213_an_empty_answer_is_refused_and_stays_a_draft(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    response = submit(client, headers, attempt_id, "  \n ")
    assert (response.status_code, response.json()) == (422, {"detail": "answer_empty"})
    assert stub.calls == []
    assert client.get(f"/v1/attempts/{attempt_id}", headers=headers).json()["status"] == "draft"


# Red when: ReviewSessionEndedError is swallowed in submit_attempt: the screen gets
# "attempt_not_submitted" instead of "session_ended" and says "Chưa gửi được" for an answer that
# can never be sent (review-screen maps only `session_ended` to the ended state).
def test_t213_submitting_into_a_stopped_session_is_session_ended(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    _, headers, session_id, attempt_id = opened(client, db_session)
    assert client.post(f"/v1/review-sessions/{session_id}/stop", headers=headers).status_code == 200
    response = submit(client, headers, attempt_id)
    assert (response.status_code, response.json()) == (409, {"detail": "session_ended"})
    assert stub.calls == []


# Plan D-12. Red when: GRADINGS_PER_USER is raised or not enforced: the 21st paid grading in a
# minute still reaches the AI. A failing grader keeps every call a real AI call (no grade).
def test_t213_the_21st_grading_in_a_minute_is_not_sent_to_the_ai(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    # The real limiter on the test Redis, its clock held inside one window: a fixed window
    # crossed half-way would let the 21st through.
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(get_redis(), now=lambda: NOW)
    try:
        _, headers, _, attempt_id = opened(client, db_session)
        stub.failure = NotGraded("unavailable", "timeout")
        assert submit(client, headers, attempt_id).json()["failure"] == "unavailable"
        for _ in range(19):
            client.post(f"/v1/attempts/{attempt_id}/regrade", headers=headers)
        assert len(stub.calls) == 20
        over = client.post(f"/v1/attempts/{attempt_id}/regrade", headers=headers)
        assert over.status_code == 200
        assert (over.json()["grading"], over.json()["failure"]) == ("failed", "unavailable")
        assert len(stub.calls) == 20
        # Per user: someone else is still graded.
        _, other, _, theirs = opened(client, db_session)
        stub.failure = None
        assert submit(client, other, theirs).json()["grading"] == "graded"
    finally:
        app.dependency_overrides.pop(get_rate_limiter, None)


# Plan 🟡9. Red when: GET stops reading pg_locks (`is_being_graded`), so a grading running in
# another request reads as "failed" and the screen offers "Chấm lại" (a second paid call)
# instead of reading again; or when "failed" carries a failure code it never had.
def test_t213_reading_an_attempt_being_graded_elsewhere_is_in_progress(
    client: TestClient, db_session: Session, stub: Stub, engine: Engine
) -> None:
    space, headers, _, attempt_id = opened(client, db_session)
    # Submitted without grading here: a grading in this test's own transaction would hold the
    # lock until the test ends (the outer transaction never commits).
    attempts = AttemptRepository(db_session, space.user.id)
    attempts.save_draft(uuid.UUID(attempt_id), answer_text="TCP", dont_remember=False)
    attempts.submit(uuid.UUID(attempt_id), FROZEN_NOW)
    db_session.flush()
    idle = client.get(f"/v1/attempts/{attempt_id}", headers=headers).json()
    assert (idle["grading"], idle["failure"], idle["result"]) == ("failed", None, None)
    with engine.connect() as other, other.begin():
        key = func.hashtextextended(attempt_id, GRADING_LOCK_NAMESPACE)
        assert other.scalar(select(func.pg_try_advisory_xact_lock(key)))
        busy = client.get(f"/v1/attempts/{attempt_id}", headers=headers).json()
    assert (busy["status"], busy["grading"], busy["result"]) == ("submitted", "in_progress", None)
    assert client.get(f"/v1/attempts/{attempt_id}", headers=headers).json()["grading"] == "failed"


# --- The answer is committed before grading (PLAN T2.13 "Giao dịch 1"). Real connections: the
# test's rolled-back session cannot show a commit.

NOW = datetime(2026, 11, 4, 13, 0, tzinfo=UTC)
GUARDS = [
    ("review_session", "review_session_guard"),
    ("attempt", "attempt_guard"),
    ("review_session_item", "review_session_item_append_only"),
]


@pytest.fixture
def committed(engine: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t213-tester-{uuid.uuid4()}@example.com")
        session.flush()
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam())
        question = QuestionRepository(session, user.id).add_idempotent(
            subject.id, level=1, prompt="q?", reference_answer="a", run_id=uuid.uuid4()
        )
        review = ReviewSessionRepository(session, user.id).start(date(2026, 11, 4), NOW)
        ReviewSessionItemRepository(session, user.id).add_all(review.id, [question.id])
        attempt = AttemptRepository(session, user.id).create_draft(review.id, question.id)
        ids = (user.id, attempt.id)
        session.commit()
    yield ids
    with engine.begin() as connection:
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": ids[0]})
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))


# Red when: `session.commit()` before grading in submit_attempt is dropped (or made a flush):
# grading that raises then rolls the request back, and the answer the user sent is lost.
def test_t213_the_answer_is_kept_when_grading_raises(
    engine: Engine, committed: tuple[uuid.UUID, uuid.UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, attempt_id = committed

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("grading crashed")

    monkeypatch.setattr(attempts_api, "grade_attempt", broken)
    with Session(engine, expire_on_commit=False) as session:
        user = session.get(User, user_id)
        assert user is not None
        try:
            with pytest.raises(RuntimeError):
                attempts_api.submit_attempt(
                    attempt_id,
                    AnswerIn(answer_text="Câu đã gửi", dont_remember=False),
                    user,
                    session,
                    NOW,
                    None,  # type: ignore[arg-type]
                    None,  # type: ignore[arg-type]
                )
        finally:
            session.rollback()  # what get_session does when the route raises
    with Session(engine) as fresh:
        kept = fresh.get(Attempt, attempt_id)
        assert kept is not None
        assert (kept.status, kept.answer_text) == ("submitted", "Câu đã gửi")


# US-04 AC2 (sources of "Không nhớ" = every source of *this* question). Red when:
# `AnchorRepository.of_units` drops its `unit_id IN (...)` filter: "Không nhớ" then shows every
# source the user has, from other questions and subjects.
def test_us04_ac2_dont_remember_shows_only_this_questions_sources(
    client: TestClient, db_session: Session, stub: Stub
) -> None:
    space, headers, _, attempt_id = opened(client, db_session)
    space.question(space.subject("Hệ điều hành"), "Tiến trình")
    result = submit(client, headers, attempt_id, "", forgot=True).json()["result"]
    assert [s["quote_text"] for s in result["sources"]] == ["TCP là một khái niệm của môn."]


# Plan 🟡9 (commit 55964c3 "pg_locks read in this database"). Red when: the `database = ...`
# condition is dropped from `is_being_graded`: a lock with the same key in another database on
# the server (another service, another test run) makes an idle attempt read "in_progress".
def test_t213_a_lock_in_another_database_is_not_a_grading_here(
    client: TestClient, db_session: Session, engine: Engine
) -> None:
    space, headers, _, attempt_id = opened(client, db_session)
    attempts = AttemptRepository(db_session, space.user.id)
    attempts.save_draft(uuid.UUID(attempt_id), answer_text="TCP", dont_remember=False)
    attempts.submit(uuid.UUID(attempt_id), FROZEN_NOW)
    db_session.flush()
    elsewhere = create_engine(engine.url.set(database="postgres"))
    try:
        with elsewhere.connect() as other, other.begin():
            key = func.hashtextextended(attempt_id, GRADING_LOCK_NAMESPACE)
            assert other.scalar(select(func.pg_try_advisory_xact_lock(key)))
            body = client.get(f"/v1/attempts/{attempt_id}", headers=headers).json()
    finally:
        elsewhere.dispose()
    assert body["grading"] == "failed"
