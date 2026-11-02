# ruff: noqa: F811
# pyright: reportUnusedImport=false
"""T8.4b tester: edges of the practice retry job the coder's tests leave open (US-05 AC14,
review Y-T1, plan review O1). ai-service and the limiter are fakes: no model is called."""

import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, event, select, text
from sqlalchemy.orm import Session
from test_t84_practice_api import FakeAi, Learner, ai, count, learner  # noqa: F401
from test_t84b_retry import Boom, Limiter, boom, job_of, queued  # noqa: F401

import core_api.jobs.practice_grade_retry as retry_module
import core_api.jobs.registry  # registers kinds
from core_api.api.ping import get_ai_client
from core_api.api.practice import DRAFTS_PER_USER
from core_api.clients.ai_client import NotGraded
from core_api.clients.practice_contract import PracticeGradeReply
from core_api.db.models import Grade
from core_api.jobs.app import app as jobs_app
from core_api.jobs.practice_grade_retry import BATCH, PRACTICE_GRADE_RETRY, retry_pending
from core_api.main import app
from core_api.repositories.review import GradeRepository
from core_api.security.rate_limit import RateLimit, RateLimiter, RateLimiterUnavailableError


def now() -> datetime:
    return datetime.now(UTC)


class Picky(FakeAi):
    """ai-service that times out on one answer only ("A"), like an answer that makes the model
    time out every time, and grades every other answer."""

    def grade_practice(self, payload: dict[str, object]) -> PracticeGradeReply | NotGraded:
        if payload["answer"] == "A":
            self.graded.append(payload)
            return NotGraded("unavailable", "timeout")
        return super().grade_practice(payload)


def place(session: Session, attempt_id: str, at: datetime) -> None:
    """Pin a job's place in the queue: created and last touched at `at`."""
    job = job_of(session, attempt_id)
    assert job is not None
    job.created_at = job.updated_at = at
    session.commit()  # kept even when the job rolls a failed row back


def test_an_answer_the_ai_always_times_out_on_does_not_starve_the_ones_behind(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # Review Y-T1 / plan review O1(a). Red when: the queue is read oldest-created first (or the
    # halted row is not pushed back), so answer A, which halts every run, is first every run and
    # answer B behind it is never graded.
    picky = Picky()
    app.dependency_overrides[get_ai_client] = lambda: picky  # the `ai` fixture removes it
    first, second = queued(learner, picky, "A"), queued(learner, picky, "B")
    start = now() - timedelta(hours=1)
    # B is written first, A last: a query with no ORDER BY (table order) would read B first.
    place(db_session, second, start + timedelta(minutes=1))
    place(db_session, first, start)
    report = retry_pending(db_session, picky, Limiter(), now())
    assert report.halted and [p["answer"] for p in picky.graded] == ["A"]
    report = retry_pending(db_session, picky, Limiter(), now())
    assert [p["answer"] for p in picky.graded] == ["A", "B", "A"]
    assert report.graded == 1 and report.halted
    assert job_of(db_session, second) is None and job_of(db_session, first) is not None
    [grade] = db_session.scalars(select(Grade)).all()
    assert str(grade.attempt_id) == second


def test_a_row_that_raises_goes_behind_the_others_for_the_next_run(
    learner: Learner, db_session: Session, boom: Boom
) -> None:
    # Plan review O1(b). Red when: the row that raised keeps its place, so with a full batch it is
    # picked first again every run and the rows behind it wait for ever.
    bad, good = queued(learner, boom, "boom"), queued(learner, boom)
    start = now() - timedelta(hours=1)
    place(db_session, bad, start)
    place(db_session, good, start + timedelta(minutes=1))
    boom.armed = True
    retry_pending(db_session, boom, Limiter(), now(), batch=1)
    assert job_of(db_session, good) is not None
    report = retry_pending(db_session, boom, Limiter(), now(), batch=1)
    assert report.graded == 1 and job_of(db_session, good) is None


def test_one_run_calls_the_ai_at_most_batch_times(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14, 2 USD budget. Red when: a run ignores its batch size and grades the whole queue.
    waiting = [queued(learner, ai) for _ in range(3)]
    report = retry_pending(db_session, ai, Limiter(), now(), batch=2)
    assert report.graded == 2 and len(ai.graded) == 2
    assert sum(job_of(db_session, attempt) is not None for attempt in waiting) == 1


@pytest.mark.parametrize(("age", "tried"), [(timedelta(days=6), True), (timedelta(days=8), False)])
def test_the_job_gives_up_after_seven_days(
    learner: Learner, db_session: Session, ai: FakeAi, age: timedelta, tried: bool
) -> None:
    # Plan decision (7 days). Red when: the give-up age is not 7 days (a 6-day-old answer is given
    # up, or an 8-day-old one still costs a call).
    attempt = queued(learner, ai)
    job = job_of(db_session, attempt)
    assert job is not None
    job.created_at = now() - age
    db_session.flush()
    retry_pending(db_session, ai, Limiter(), now())
    assert (len(ai.graded) == 1) is tried
    job = job_of(db_session, attempt)
    if tried:
        assert job is None and count(db_session, Grade) == 1
    else:
        assert job is not None and (job.status, job.failure) == ("failed", "unavailable")


def test_practice_grade_retry_is_registered_every_ten_minutes() -> None:
    # Plan decisions (cron 10 min, batch 20, drafts 10/min). Red when: the registry does not import
    # the job (the worker never runs it, every queued answer waits for ever), it runs on another
    # schedule, or a budget bound (calls per run, drafts per minute) is raised.
    assert hasattr(core_api.jobs.registry, "practice_grade_retry")
    assert BATCH == 20
    assert (DRAFTS_PER_USER.limit, DRAFTS_PER_USER.window) == (10, timedelta(minutes=1))
    registry: Any = jobs_app.periodic_registry
    key = (PRACTICE_GRADE_RETRY, PRACTICE_GRADE_RETRY)
    assert registry.periodic_tasks[key].cron == "*/10 * * * *"


def test_the_job_reads_its_row_with_skip_locked(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # Plan review O1, "SKIP LOCKED". Red when: the job locks its row with a plain FOR UPDATE and so
    # waits behind a request (Chấm lại, submit) that holds it, instead of going on to the next one.
    # (A two-connection test needs committed submitted attempts, which the append-only guards never
    # let a teardown delete; the statement is checked instead.)
    queued(learner, ai)
    seen: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
        seen.append(statement)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", record)
    try:
        assert retry_pending(db_session, ai, Limiter(), now()).graded == 1
    finally:
        event.remove(connection, "before_cursor_execute", record)
    locking = [s for s in seen if "FROM grade_job" in s and "FOR UPDATE" in s]
    assert locking and all("SKIP LOCKED" in s for s in locking)


def test_a_row_another_request_is_grading_does_not_stop_the_run(
    learner: Learner, db_session: Session, ai: FakeAi, monkeypatch: pytest.MonkeyPatch
) -> None:
    # US-05 AC14. Red when: a row whose grading lock a "Chấm lại" holds is treated as "the AI has
    # no turn": the run halts there and the answers behind it wait for the next run.
    busy, free = queued(learner, ai), queued(learner, ai)
    start = now() - timedelta(hours=1)
    place(db_session, busy, start)
    place(db_session, free, start + timedelta(minutes=1))
    real = GradeRepository.try_lock_attempt

    def lock(self: GradeRepository, attempt_id: uuid.UUID) -> bool:
        return str(attempt_id) != busy and real(self, attempt_id)

    monkeypatch.setattr(GradeRepository, "try_lock_attempt", lock)
    report = retry_pending(db_session, ai, Limiter(), now())
    assert report.graded == 1 and not report.halted
    assert job_of(db_session, free) is None and job_of(db_session, busy) is not None


def test_the_last_row_of_a_run_is_committed(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14. Red when: the job does not commit the last row it settles: the worker's session
    # closes, the row is rolled back, and the next run pays for the same grading again.
    attempt = queued(learner, ai)
    assert retry_pending(db_session, ai, Limiter(), now()).graded == 1
    db_session.rollback()  # what closing the worker's session does to anything not committed
    assert job_of(db_session, attempt) is None and count(db_session, Grade) == 1


def test_an_answer_with_no_grade_and_nothing_queued_reloads_failed(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14 (plan review O2). Red when: an answer nothing will ever grade (an attempt from
    # before the queue, its row gone) reloads as "pending", promising a grading that never comes.
    attempt = queued(learner, ai)
    job = job_of(db_session, attempt)
    assert job is not None
    db_session.delete(job)
    db_session.commit()
    read = learner.client.get(f"/v1/practice/attempts/{attempt}", headers=learner.headers)
    assert read.json()["grading"] == "failed"


def test_the_failure_log_line_holds_no_exception_text(
    learner: Learner, db_session: Session, boom: Boom, log_output: Callable[[], str]
) -> None:
    # ADR-0013. Red when: the job writes the exception text (which can quote the answer) into an
    # allowed field such as `error_type`; caplog.text shows the message only, the JSON line shows
    # every allowed extra.
    queued(learner, boom, "boom")
    boom.armed = True
    retry_pending(db_session, boom, Limiter(), now())
    [line] = [json.loads(x) for x in log_output().splitlines() if "practice grade retry" in x]
    assert "secret answer text" not in json.dumps(line, ensure_ascii=False)
    assert line["error_type"] == "RuntimeError"


def test_the_failure_log_line_names_the_attempt(
    learner: Learner, db_session: Session, boom: Boom, log_output: Callable[[], str]
) -> None:
    # Plan review O1 (log id + type only). Red when: the id of the row that raised is missing from
    # the line (`attempt_id` must be an allowed log field), so nobody can find the poison row.
    attempt = queued(learner, boom, "boom")
    boom.armed = True
    retry_pending(db_session, boom, Limiter(), now())
    [line] = [json.loads(x) for x in log_output().splitlines() if "practice grade retry" in x]
    assert line["attempt_id"] == attempt, line


class Down:
    """A limiter whose Redis does not answer."""

    def enforce(self, rule: RateLimit, key: str) -> None:
        raise RateLimiterUnavailableError


def test_a_limiter_that_cannot_answer_means_no_call_and_no_error(
    learner: Learner, db_session: Session, ai: FakeAi, caplog: pytest.LogCaptureFixture
) -> None:
    # Budget, rate limits fail closed. Red when: Redis being down lets the job call the AI (fail
    # open), or each answer is logged as a broken row instead of waiting for the next run.
    attempt = queued(learner, ai)
    with caplog.at_level(logging.DEBUG, logger="core_api.jobs"):
        report = retry_pending(db_session, ai, Down(), now())
    job = job_of(db_session, attempt)
    assert ai.graded == [] and job is not None and job.status == "queued"
    assert report.graded == report.failed == 0
    assert "practice grade retry failed" not in caplog.text


class Rules:
    """A limiter that lets everything through and remembers each (rule, key)."""

    def __init__(self) -> None:
        self.hits: list[tuple[str, str]] = []

    def enforce(self, rule: RateLimit, key: str) -> None:
        self.hits.append((rule.name, key))


def test_the_job_spends_the_grading_limit_of_the_answers_owner(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14, ADR-0014. Red when: the job grades under another bucket than `grade_user` (or
    # another key than the owner's id), so a user's queued answers bypass their grading limit.
    queued(learner, ai)
    rules = Rules()
    assert retry_pending(db_session, ai, rules, now()).graded == 1
    assert rules.hits == [("grade_user", str(learner.user.id))]


def test_a_row_that_breaks_in_the_database_still_goes_behind(
    learner: Learner, db_session: Session, ai: FakeAi, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Plan review O1(b). Red when: after a database error on one row the job does not roll back
    # before pushing the row back, the push-back fails on the broken transaction, the row keeps
    # its place, and with a full batch the rows behind it wait for ever.
    bad, good = queued(learner, ai), queued(learner, ai)
    start = now() - timedelta(hours=1)
    place(db_session, bad, start)
    place(db_session, good, start + timedelta(minutes=1))
    real = GradeRepository.try_lock_attempt

    def lock(self: GradeRepository, attempt_id: uuid.UUID) -> bool:
        if str(attempt_id) == bad:
            self.session.execute(text("SELECT 1 / 0"))
        return real(self, attempt_id)

    monkeypatch.setattr(GradeRepository, "try_lock_attempt", lock)
    retry_pending(db_session, ai, Limiter(), now(), batch=1)
    assert job_of(db_session, good) is not None
    report = retry_pending(db_session, ai, Limiter(), now(), batch=1)
    assert report.graded == 1 and job_of(db_session, good) is None


class Client:
    closed = False

    def close(self) -> None:
        self.closed = True


def test_the_worker_entry_runs_with_an_aware_clock_and_closes_the_client(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    # US-05 AC14 (the cron entry nothing else calls). Red when: the worker passes a naive clock
    # (every row then breaks on `now - created_at` and nothing is ever graded), a limiter other
    # than the Redis one, or leaves the AI client open when the run raises.
    client = Client()
    seen: dict[str, Any] = {}

    def fake_retry(session: Session, ai: object, limiter: object, at: datetime) -> None:
        seen.update(ai=ai, limiter=limiter, at=at)
        raise RuntimeError("stop")

    def build(settings: object) -> Client:
        return client

    monkeypatch.setattr(retry_module.AiServiceClient, "from_settings", build)
    monkeypatch.setattr(retry_module, "get_redis", lambda: object())
    monkeypatch.setattr(retry_module, "get_engine", lambda: engine)
    monkeypatch.setattr(retry_module, "retry_pending", fake_retry)
    with pytest.raises(RuntimeError):
        retry_module.practice_grade_retry_job({})
    assert seen["ai"] is client and client.closed
    assert isinstance(seen["limiter"], RateLimiter)
    assert seen["at"].tzinfo is not None


def test_a_row_that_keeps_raising_is_given_up_after_a_few_runs(
    learner: Learner, db_session: Session, boom: Boom
) -> None:
    # Final review F3. Red when: a row that raises keeps costing a call to the AI every run for the
    # whole 7 days (the call is spent before the raise, nothing is saved).
    from core_api.jobs.practice_grade_retry import MAX_ERRORS

    attempt = queued(learner, boom, "boom")
    boom.armed = True
    calls = 0
    original = boom.grade_practice

    def counting(payload: dict[str, object]) -> PracticeGradeReply | NotGraded:
        nonlocal calls
        calls += 1
        return original(payload)

    boom.grade_practice = counting  # type: ignore[method-assign]
    errors: dict[uuid.UUID, int] = {}
    trail: list[object] = []
    for _ in range(MAX_ERRORS + 3):
        rep = retry_pending(db_session, boom, Limiter(), now(), errors=errors)
        trail.append((calls, list(errors.values()), rep.failed, rep.skipped))
    row = job_of(db_session, attempt)
    assert row is not None and row.status == "failed" and row.failure == "unavailable", trail
    assert calls == MAX_ERRORS, trail


def test_the_summary_log_line_keeps_its_counters(
    learner: Learner, db_session: Session, ai: FakeAi, log_output: Callable[[], str]
) -> None:
    # Final review F2. Red when: the counter names are not allowed log fields and are dropped.
    from core_api.jobs.practice_grade_retry import practice_grade_retry_job  # noqa: F401
    from core_api.logging import ALLOWED_FIELDS

    assert {"graded_count", "failed_count", "skipped_count", "halted"} <= ALLOWED_FIELDS
