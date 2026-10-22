"""R05 (T1.21, plan D8/D9): a periodic job counts failed and stalled jobs, so a broken send_email
shows up as an ERROR line in the logs instead of only when a user complains.

Rows are written straight into procrastinate's tables, with set times, on a real PostgreSQL.
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.jobs.app import app
from core_api.jobs.job_health import JOB_HEALTH, JobHealth, job_health, report_job_health

pytestmark = pytest.mark.usefixtures("clean_jobs")

NOW = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)
SECRET = "someone-private@example.com"


def add_job(engine: Engine, status: str, *, worker: int | None = None) -> int:
    with engine.begin() as connection:
        return connection.execute(
            text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, args, status, worker_id)"
                " VALUES ('default', 'send_email', CAST(:args AS jsonb), CAST(:status AS"
                " procrastinate_job_status), :worker) RETURNING id"
            ),
            {"args": json.dumps({"email": SECRET}), "status": status, "worker": worker},
        ).scalar_one()


def add_event(engine: Engine, job: int, kind: str, at: datetime) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO procrastinate_events (job_id, type, at)"
                " VALUES (:job, CAST(:kind AS procrastinate_job_event_type), :at)"
            ),
            {"job": job, "kind": kind, "at": at},
        )


def add_worker(engine: Engine, heartbeat: datetime) -> int:
    with engine.begin() as connection:
        return connection.execute(
            text("INSERT INTO procrastinate_workers (last_heartbeat) VALUES (:at) RETURNING id"),
            {"at": heartbeat},
        ).scalar_one()


def health(engine: Engine) -> JobHealth:
    with Session(engine) as session:
        return job_health(session, NOW)


def test_r05_failed_in_last_20_minutes_is_counted(engine: Engine) -> None:
    # Red when: failures are not counted, or not counted inside the 20-minute window.
    add_event(engine, add_job(engine, "failed"), "failed", NOW - timedelta(minutes=19))
    assert health(engine).failed_recent == 1


def test_r05_older_failed_is_not(engine: Engine) -> None:
    # Red when: every failure ever counts, so one old failure is an ERROR forever.
    add_event(engine, add_job(engine, "failed"), "failed", NOW - timedelta(minutes=21))
    result = health(engine)
    assert (result.failed_recent, result.failed_total) == (0, 1)


def test_r05_doing_without_worker_heartbeat_is_stalled(engine: Engine) -> None:
    # Red when: a job whose worker died is never reported.
    lost = add_worker(engine, NOW - timedelta(minutes=6))
    add_job(engine, "doing", worker=lost)
    add_job(engine, "doing", worker=None)  # its worker was deleted (ON DELETE SET NULL)
    assert health(engine).stalled == 2


def test_r05_long_job_with_live_heartbeat_is_not(engine: Engine) -> None:
    # Red when: "doing for more than 10 minutes" counts, and a long LLM job (M4) is an ERROR.
    alive = add_worker(engine, NOW - timedelta(seconds=20))
    job = add_job(engine, "doing", worker=alive)
    add_event(engine, job, "started", NOW - timedelta(hours=1))
    assert health(engine).stalled == 0


def test_r05_quiet_when_healthy(
    engine: Engine, log_output: Callable[[], str], caplog: pytest.LogCaptureFixture
) -> None:
    # Red when: a healthy queue logs at ERROR.
    add_job(engine, "succeeded")
    with caplog.at_level(logging.INFO, logger="core_api.jobs"):
        report_job_health(engine, NOW)
    lines = [json.loads(line) for line in log_output().splitlines() if line]
    health_lines = [line for line in lines if line["message"].startswith("job queue")]
    assert [line["level"] for line in health_lines] == ["INFO"]


def test_r05_failed_job_logs_error_with_counts_and_no_args(
    engine: Engine, log_output: Callable[[], str], caplog: pytest.LogCaptureFixture
) -> None:
    # Red when: an unhealthy queue is not an ERROR, a count is missing from the line, or the
    # job's arguments (an email address) reach the log (review plan P5).
    add_event(engine, add_job(engine, "failed"), "failed", NOW - timedelta(minutes=1))
    with caplog.at_level(logging.INFO, logger="core_api.jobs"):
        report_job_health(engine, NOW)
    output = log_output()
    [line] = [json.loads(line) for line in output.splitlines() if "job queue" in line]
    assert line["level"] == "ERROR"
    assert (line["jobs_failed_recent"], line["jobs_failed_total"], line["jobs_stalled"]) == (
        1,
        1,
        0,
    )
    assert SECRET not in output and "s***@" not in output


def test_r05_runs_every_15_minutes() -> None:
    # Red when: the job is not registered with the worker, or on another schedule.
    registry: Any = app.periodic_registry  # Procrastinate leaves its task types unparametrised
    assert registry.periodic_tasks[(JOB_HEALTH, JOB_HEALTH)].cron == "*/15 * * * *"


def test_r05_without_a_given_time_it_uses_the_database_clock(engine: Engine) -> None:
    # Red when: the scheduled run compares the worker's clock with times Postgres wrote; a
    # worker clock 5 minutes off would call every running job stalled (review f70c519).
    alive = add_worker(engine, datetime.now(UTC) - timedelta(seconds=20))
    add_job(engine, "doing", worker=alive)
    with Session(engine) as session:
        assert job_health(session).stalled == 0
