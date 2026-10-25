"""The `job_health` job (T1.21, risk register R05): failed and stalled jobs, counted.

ADR-0013 lists "failed jobs" among what must be measured. Until metrics have somewhere to go
(ADR-0015, T0.14), this job counts them every 15 minutes and logs one line: ERROR when something
needs a look, INFO otherwise. The deploy's alert (T0.13) watches for that ERROR.

- failed_recent: `failed` events in the last 20 minutes. The window overlaps the 15-minute
  schedule, so a missed run loses nothing; a failure may be counted twice, never zero times.
- failed_total: jobs left in `failed`, for context only (one old failure is not an alarm).
- stalled: jobs `doing` whose worker stopped beating (plan D8). "Doing for N minutes" would
  report a long job (an LLM call, M4) that is still running fine.
- outbox_unsent_stale: outbox rows still unsent 5 minutes after their event (T4.2, plan Y8).
  The relay sends within a second or two, or backs off 30 s at most, so this means the relay
  or Redis is down and events are piling up. The count includes no event, only rows.

Only counts are read and logged, never a job's arguments: they hold email addresses (P5).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.db.engine import get_engine
from core_api.jobs.handler import periodic_job

JOB_HEALTH = "job_health"
RECENT_FAILURES = timedelta(minutes=20)
# Procrastinate beats every 10 s by default; minutes of silence means the worker is gone.
STALLED_AFTER = timedelta(minutes=5)
OUTBOX_STALE_AFTER = timedelta(minutes=5)

_log = logging.getLogger("core_api.jobs")


@dataclass(frozen=True)
class JobHealth:
    failed_recent: int
    failed_total: int
    stalled: int
    outbox_unsent_stale: int

    @property
    def needs_a_look(self) -> bool:
        return self.failed_recent > 0 or self.stalled > 0 or self.outbox_unsent_stale > 0


def job_health(session: Session, now: datetime | None = None) -> JobHealth:
    """Counts as of `now`; without one, as of the database's clock, which wrote the times it
    compares (a worker's clock a few minutes off would otherwise call live jobs stalled)."""
    counts = session.execute(
        text(
            """
            WITH t AS (SELECT COALESCE(CAST(:now AS timestamptz), now()) AS now)
            SELECT
              (SELECT count(*) FROM procrastinate_events, t
                 WHERE type = 'failed' AND at >= t.now - :recent) AS failed_recent,
              (SELECT count(*) FROM procrastinate_jobs WHERE status = 'failed') AS failed_total,
              (SELECT count(*) FROM procrastinate_jobs j
                 LEFT JOIN procrastinate_workers w ON w.id = j.worker_id, t
                 WHERE j.status = 'doing'
                   AND (w.id IS NULL OR w.last_heartbeat < t.now - :stalled)) AS stalled,
              (SELECT count(*) FROM outbox, t
                 WHERE sent_at IS NULL AND occurred_at < t.now - :outbox_stale)
                 AS outbox_unsent_stale
            """
        ),
        {
            "now": now,
            "recent": RECENT_FAILURES,
            "stalled": STALLED_AFTER,
            "outbox_stale": OUTBOX_STALE_AFTER,
        },
    ).one()
    return JobHealth(
        counts.failed_recent, counts.failed_total, counts.stalled, counts.outbox_unsent_stale
    )


def report_job_health(engine: Engine, now: datetime | None = None) -> JobHealth:
    with Session(engine) as session:
        health = job_health(session, now)
    fields = {
        "jobs_failed_recent": health.failed_recent,
        "jobs_failed_total": health.failed_total,
        "jobs_stalled": health.stalled,
        "outbox_unsent_stale": health.outbox_unsent_stale,
    }
    if health.needs_a_look:
        _log.error("job queue needs a look", extra=fields)
    else:
        _log.info("job queue healthy", extra=fields)
    return health


@periodic_job(JOB_HEALTH, cron="*/15 * * * *")
def job_health_job(payload: dict[str, Any]) -> None:
    report_job_health(get_engine())
