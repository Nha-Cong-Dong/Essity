"""R05 (T1.21) edge cases the first tests leave open: the exact edges of both windows, which
events and which statuses count, and which counts make the ERROR line.

Written by the Tester (feature-tester, 23/10). Each test says which change to job_health.py
turns it red.
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.jobs.job_health import JobHealth, job_health, report_job_health

pytestmark = pytest.mark.usefixtures("clean_jobs")

NOW = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)


def add_job(engine: Engine, status: str, *, worker: int | None = None) -> int:
    with engine.begin() as connection:
        return connection.execute(
            text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, args, status, worker_id)"
                " VALUES ('default', 'send_email', '{}'::jsonb, CAST(:status AS"
                " procrastinate_job_status), :worker) RETURNING id"
            ),
            {"status": status, "worker": worker},
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


def health_lines(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if "job queue" in line]


def test_r05_failure_exactly_20_minutes_ago_is_still_counted_and_one_second_older_is_not(
    engine: Engine,
) -> None:
    # Red when: the window test `at >= now - 20 min` becomes `>` (the overlap with the 15-minute
    # schedule then has a one-instant hole) or the window grows or shrinks by a minute.
    job = add_job(engine, "failed")
    add_event(engine, job, "failed", NOW - timedelta(minutes=20))
    add_event(engine, job, "failed", NOW - timedelta(minutes=20, seconds=1))
    assert health(engine).failed_recent == 1


def test_r05_only_failed_events_count(engine: Engine) -> None:
    # Red when: the `type = 'failed'` condition is dropped, so every event in the window (a retry
    # being scheduled, a job starting) is a failure and a busy queue is always an ERROR.
    job = add_job(engine, "succeeded")
    for kind in ("deferred", "started", "deferred_for_retry", "succeeded"):
        add_event(engine, job, kind, NOW - timedelta(minutes=1))
    assert health(engine).failed_recent == 0


def test_r05_a_heartbeat_4_minutes_old_is_alive_and_6_is_stalled(engine: Engine) -> None:
    # Red when: STALLED_AFTER shrinks (a worker a bit slow to beat is called dead) or grows past
    # six minutes (a dead worker goes unreported for an hour).
    slow = add_worker(engine, NOW - timedelta(minutes=4))
    dead = add_worker(engine, NOW - timedelta(minutes=6))
    add_job(engine, "doing", worker=slow)
    add_job(engine, "doing", worker=dead)
    assert health(engine).stalled == 1


def test_r05_only_doing_jobs_can_be_stalled(engine: Engine) -> None:
    # Red when: the `status = 'doing'` condition is dropped: every waiting, finished or failed
    # job (none has a worker) would be counted as stalled.
    for status in ("todo", "succeeded", "failed", "aborted"):
        add_job(engine, status)
    assert health(engine).stalled == 0


def test_r05_an_empty_queue_counts_zero(engine: Engine) -> None:
    # Red when: the counts become NULL or the query breaks without a single row to count.
    assert health(engine) == JobHealth(0, 0, 0, 0)


def test_r05_a_stalled_job_alone_is_an_error(
    engine: Engine, log_output: Callable[[], str], caplog: pytest.LogCaptureFixture
) -> None:
    # Red when: `needs_a_look` ignores `stalled` (a dead worker with no failure logs at INFO).
    add_job(engine, "doing")  # worker is NULL: it was deleted
    with caplog.at_level(logging.INFO, logger="core_api.jobs"):
        report_job_health(engine, NOW)
    [line] = health_lines(log_output())
    assert (line["level"], line["jobs_stalled"], line["jobs_failed_recent"]) == ("ERROR", 1, 0)


def test_r05_an_old_failure_alone_stays_at_info(
    engine: Engine, log_output: Callable[[], str], caplog: pytest.LogCaptureFixture
) -> None:
    # Red when: `jobs_failed_total` makes the ERROR (one failure from last week would alarm until
    # someone deletes the row).
    add_event(engine, add_job(engine, "failed"), "failed", NOW - timedelta(days=7))
    with caplog.at_level(logging.INFO, logger="core_api.jobs"):
        report_job_health(engine, NOW)
    [line] = health_lines(log_output())
    assert (line["level"], line["jobs_failed_total"], line["jobs_failed_recent"]) == ("INFO", 1, 0)


def test_r05_a_recent_failure_alone_is_an_error(
    engine: Engine, log_output: Callable[[], str], caplog: pytest.LogCaptureFixture
) -> None:
    # Red when: `needs_a_look` ignores `failed_recent`.
    add_event(engine, add_job(engine, "failed"), "failed", NOW - timedelta(minutes=2))
    with caplog.at_level(logging.INFO, logger="core_api.jobs"):
        report_job_health(engine, NOW)
    [line] = health_lines(log_output())
    assert line["level"] == "ERROR"
