# ruff: noqa: F811
# pyright: reportUnusedImport=false
"""T8.4b: the retry job grades queued practice answers when there is a turn (US-05 AC14, ADR-0013,
ADR-0014; plan review O1/O3/Y3). ai-service and the limiter are fakes: no model is called."""

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t84_practice_api import FakeAi, Learner, ai, count, learner  # noqa: F401

from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import NotGraded
from core_api.clients.practice_contract import PracticeGradeReply
from core_api.db.models import Attempt, Grade, GradeJob, PracticeLog, Question, Subject, User
from core_api.jobs.practice_grade_retry import MAX_AGE, retry_pending
from core_api.main import app
from core_api.repositories.review import GradeRepository
from core_api.security.rate_limit import RateLimitedError

QUOTA = NotGraded("quota", "quota_hard_cap")


class Limiter:
    def __init__(self, blocked: set[str] | None = None) -> None:
        self.blocked = blocked or set()

    def enforce(self, rule: object, key: str) -> None:
        if key in self.blocked:
            raise RateLimitedError(60)


class Boom(FakeAi):
    """Raises for the answer "boom", like a request that breaks inside grading."""

    armed = False

    def grade_practice(self, payload: dict[str, object]) -> PracticeGradeReply | NotGraded:
        if self.armed and payload["answer"] == "boom":
            raise RuntimeError("secret answer text")
        return super().grade_practice(payload)


@pytest.fixture
def boom(client: TestClient) -> Iterator[Boom]:
    fake = Boom()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


def now() -> datetime:
    return datetime.now(UTC)


def queued(learner: Learner, ai: FakeAi, text: str = "SYN, SYN-ACK, ACK") -> str:
    """A submitted practice answer waiting in the queue (the AI was out of turns)."""
    before = ai.verdicts
    ai.verdicts = QUOTA
    attempt = learner.submit(learner.open(learner.question())["attempt_id"], text)
    ai.verdicts = before
    ai.graded.clear()  # the call that found no turn is not the job's
    assert attempt["grading"] == "pending"
    return attempt["attempt_id"]


def job_of(session: Session, attempt_id: str) -> GradeJob | None:
    session.expire_all()
    return session.scalars(
        select(GradeJob).where(GradeJob.attempt_id == uuid.UUID(attempt_id))
    ).one_or_none()


def test_retry_grades_when_budget_returns_and_deletes_job(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14. Red when: a queued answer is not graded once, its schedule not moved once, or
    # its job row stays. Also: running the job again changes nothing (never graded twice).
    attempt = queued(learner, ai)
    report = retry_pending(db_session, ai, Limiter(), now())
    assert report.graded == 1
    assert job_of(db_session, attempt) is None
    assert count(db_session, Grade) == 1 and count(db_session, PracticeLog) == 1
    retry_pending(db_session, ai, Limiter(), now())
    assert count(db_session, Grade) == 1 and count(db_session, PracticeLog) == 1
    assert len(ai.graded) == 1
    read = learner.client.get(f"/v1/practice/attempts/{attempt}", headers=learner.headers)
    assert read.json()["grading"] == "graded"


def test_retry_stops_run_when_ai_has_no_turn(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14. Red when: an AI that is out of budget is called once per queued answer.
    first, second = queued(learner, ai), queued(learner, ai)
    ai.verdicts = QUOTA
    report = retry_pending(db_session, ai, Limiter(), now())
    assert report.halted and len(ai.graded) == 1
    assert job_of(db_session, first) is not None and job_of(db_session, second) is not None


def test_retry_respects_user_limiter_and_other_users(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14, ADR-0014. Red when: a user over the limit blocks another user's answer, or an
    # answer is graded for the wrong user.
    mine = queued(learner, ai)
    other = Learner(learner.client, db_session)
    theirs = queued(other, ai)
    report = retry_pending(db_session, ai, Limiter({str(learner.user.id)}), now())
    assert report.graded == 1 and not report.halted
    assert job_of(db_session, mine) is not None and job_of(db_session, theirs) is None
    [grade] = db_session.scalars(select(Grade)).all()
    assert str(grade.attempt_id) == theirs and grade.user_id == other.user.id


def test_retry_skips_review_attempts_and_file_backed_jobs(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14. Red when: a job holding a request file (the review path, T4.19) is touched.
    attempt = queued(learner, ai)
    job = job_of(db_session, attempt)
    assert job is not None
    job.request_key = "users/x/grading/y/request.json"
    db_session.flush()
    retry_pending(db_session, ai, Limiter(), now())
    assert ai.graded == [] and job_of(db_session, attempt) is not None


def test_permanent_failure_marks_job_failed_and_view_says_failed(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14. Red when: an answer that can never be graded stays queued for ever.
    attempt = queued(learner, ai)
    ai.verdicts = NotGraded("invalid", "bad")
    retry_pending(db_session, ai, Limiter(), now())
    job = job_of(db_session, attempt)
    assert job is not None and (job.status, job.failure) == ("failed", "invalid")
    read = learner.client.get(f"/v1/practice/attempts/{attempt}", headers=learner.headers)
    assert read.json()["grading"] == "failed"
    retry_pending(db_session, ai, Limiter(), now())
    assert len(ai.graded) == 1


def test_disabled_ai_halts_without_failing_jobs(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # Plan review Y2. Red when: AI switched off in configuration fails every queued answer.
    attempt = queued(learner, ai)
    ai.verdicts = NotGraded("disabled", "off")
    report = retry_pending(db_session, ai, Limiter(), now())
    job = job_of(db_session, attempt)
    assert report.halted and job is not None and job.status == "queued"


def test_job_older_than_limit_fails_unavailable(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14. Red when: a job older than MAX_AGE is still tried.
    attempt = queued(learner, ai)
    job = job_of(db_session, attempt)
    assert job is not None
    job.created_at = now() - MAX_AGE - timedelta(minutes=1)
    db_session.flush()
    retry_pending(db_session, ai, Limiter(), now())
    job = job_of(db_session, attempt)
    assert ai.graded == []
    assert job is not None and (job.status, job.failure) == ("failed", "unavailable")


def test_retry_poison_item_does_not_block_queue(
    learner: Learner, db_session: Session, boom: Boom
) -> None:
    # Plan review O1. Red when: one item that raises starves the ones behind it.
    bad, good = queued(learner, boom, "boom"), queued(learner, boom)
    boom.armed = True
    for _ in range(2):
        retry_pending(db_session, boom, Limiter(), now())
    assert job_of(db_session, bad) is not None and job_of(db_session, good) is None


def test_retry_skips_deleted_user_subject_and_retired_question(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # Plan review O3, ADR-0001/0007. Red when: an answer of a deleted account or subject, or of a
    # question marked worthless, is sent to the AI.
    others = [Learner(learner.client, db_session) for _ in range(3)]
    gone_user, gone_subject, retired = (
        queued(learner, ai),
        queued(others[0], ai),
        queued(others[1], ai),
    )
    live = queued(others[2], ai)
    user = db_session.get(User, learner.user.id)
    subject = db_session.get(Subject, others[0].subject)
    attempt = db_session.get(Attempt, uuid.UUID(retired))
    assert user is not None and subject is not None and attempt is not None
    question = db_session.get(Question, attempt.question_id)
    assert question is not None
    user.deleted_at = subject.deleted_at = now()
    question.status = "retired"
    db_session.flush()
    retry_pending(db_session, ai, Limiter(), now())
    assert len(ai.graded) == 1 and job_of(db_session, live) is None
    for attempt_id in (gone_user, gone_subject, retired):
        job = job_of(db_session, attempt_id)
        assert job is not None and job.status == "failed"
    assert count(db_session, PracticeLog) == 1


def test_retry_skips_an_attempt_another_request_is_grading(
    learner: Learner, db_session: Session, ai: FakeAi, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Plan review Y3. Red when: the job grades an attempt whose grading lock another request
    # holds. (The test's own transaction would hold the advisory lock itself, so the lock is
    # reported taken instead of held from a second connection.)
    attempt = queued(learner, ai)

    def taken(self: GradeRepository, attempt_id: uuid.UUID) -> bool:
        return False

    monkeypatch.setattr(GradeRepository, "try_lock_attempt", taken)
    retry_pending(db_session, ai, Limiter(), now())
    job = job_of(db_session, attempt)
    assert ai.graded == [] and job is not None and job.status == "queued"


def test_retry_logs_hold_no_answer(
    learner: Learner, db_session: Session, boom: Boom, caplog: pytest.LogCaptureFixture
) -> None:
    # ADR-0013. Red when: a log line of the job carries the learner's answer or an exception text.
    queued(learner, boom, "boom")
    boom.armed = True
    with caplog.at_level(logging.DEBUG):
        retry_pending(db_session, boom, Limiter(), now())
    assert "secret answer text" not in caplog.text
    assert "boom" not in caplog.text.replace("Boom", "")
