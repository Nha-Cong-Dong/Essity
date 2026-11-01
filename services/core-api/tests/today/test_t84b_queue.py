"""T8.4b: a practice answer that cannot be graded now is queued in `grade_job` (US-05 AC14).
ai-service is a fake: nothing here calls a model."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t84_practice_api import FakeAi, Learner, ai, count, learner  # noqa: F401

from core_api.clients.ai_client import NotGraded
from core_api.db.models import Grade, GradeJob, PracticeLog


def jobs(session: Session) -> list[GradeJob]:
    session.expire_all()
    return list(session.scalars(select(GradeJob)))


def regrade(learner: Learner, attempt: str) -> dict[str, object]:
    response = learner.client.post(f"/v1/practice/attempts/{attempt}/regrade", headers=learner.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_pending_submit_queues_one_grade_job_without_file(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14. Red when: no job row for a pending answer, a file key, or a second row.
    attempt = learner.open(learner.question())["attempt_id"]
    ai.verdicts = NotGraded("quota", "quota_hard_cap")
    assert learner.submit(attempt)["grading"] == "pending"
    regrade(learner, attempt)  # still out of turns
    rows = jobs(db_session)
    assert len(rows) == 1
    assert (rows[0].status, rows[0].request_key, str(rows[0].attempt_id)) == ("queued", "", attempt)


def test_regrade_success_deletes_job(learner: Learner, db_session: Session, ai: FakeAi) -> None:
    # US-05 AC14. Red when: the grade exists and the job row stays.
    attempt = learner.open(learner.question())["attempt_id"]
    ai.verdicts = NotGraded("quota", "quota_hard_cap")
    learner.submit(attempt)
    ai.verdicts = ["correct", "correct"]
    assert regrade(learner, attempt)["grading"] == "graded"
    assert jobs(db_session) == [] and count(db_session, Grade) == 1


def test_first_submit_not_ready_reload_says_failed(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14 (plan review O2). Red when: a question with no rubric reloads as "pending" with
    # nothing queued, so the screen promises a grading that never comes.
    attempt = learner.open(learner.question(rubric=None))["attempt_id"]
    body = learner.submit(attempt)
    assert (body["grading"], body["failure"]) == ("failed", "not_ready")
    read = learner.client.get(f"/v1/practice/attempts/{attempt}", headers=learner.headers)
    assert read.json()["grading"] == "failed"
    [row] = jobs(db_session)
    assert (row.status, row.failure) == ("failed", "invalid")


def test_pending_attempt_reloads_pending(learner: Learner, ai: FakeAi) -> None:
    # US-05 AC14. Red when: the queued answer reloads as anything else.
    attempt = learner.open(learner.question())["attempt_id"]
    ai.verdicts = NotGraded("quota", "quota_hard_cap")
    learner.submit(attempt)
    read = learner.client.get(f"/v1/practice/attempts/{attempt}", headers=learner.headers)
    assert read.json()["grading"] == "pending"
    assert uuid.UUID(attempt) and count_logs(learner.session) == 0


def count_logs(session: Session) -> int:
    return count(session, PracticeLog)
