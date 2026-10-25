"""Outbox upkeep (T4.2): sent rows are deleted after 7 days (plan E8, Y6), and job_health reports
rows left unsent for more than 5 minutes (plan Y8), since that means the relay is down."""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

import core_api.jobs.registry  # noqa: F401  # pyright: ignore[reportUnusedImport]  # registers kinds
from core_api.db.models import Outbox
from core_api.jobs.app import app
from core_api.jobs.job_health import job_health, report_job_health
from core_api.jobs.outbox_cleanup import OUTBOX_CLEANUP, SENT_KEPT_FOR, delete_sent_outbox
from core_api.messaging.envelope import UserDeleted
from core_api.messaging.outbox import enqueue_event

pytestmark = pytest.mark.usefixtures("clean_outbox")

NOW = datetime(2026, 10, 25, 8, 30, tzinfo=UTC)


def add(engine: Engine, *, occurred_at: datetime, sent_at: datetime | None) -> uuid.UUID:
    with Session(engine) as session:
        event_id = enqueue_event(session, UserDeleted(), user_id=uuid.uuid4(), now=occurred_at)
        session.flush()
        session.execute(update(Outbox).where(Outbox.id == event_id).values(sent_at=sent_at))
        session.commit()
    return event_id


def remaining(engine: Engine) -> set[uuid.UUID]:
    with Session(engine) as session:
        return set(session.scalars(select(Outbox.id)))


def test_outbox_cleanup_deletes_only_sent_rows_older_than_7_days(engine: Engine) -> None:
    # Red when: the cleanup deletes an unsent row (an event lost, however old), a row sent less
    # than 7 days ago, or keeps old sent rows so the table only grows.
    long_ago = NOW - timedelta(days=30)
    old_sent = add(engine, occurred_at=long_ago, sent_at=NOW - SENT_KEPT_FOR - timedelta(minutes=1))
    recent_sent = add(
        engine, occurred_at=long_ago, sent_at=NOW - SENT_KEPT_FOR + timedelta(minutes=1)
    )
    old_unsent = add(engine, occurred_at=long_ago, sent_at=None)
    with Session(engine) as session:
        assert delete_sent_outbox(session, NOW) == 1
        session.commit()
    assert remaining(engine) == {recent_sent, old_unsent}
    assert old_sent not in remaining(engine)
    assert SENT_KEPT_FOR == timedelta(days=7)


def test_outbox_cleanup_is_registered_as_hourly_periodic() -> None:
    # Red when: the job is written but never scheduled (missing from jobs/registry.py, which
    # the worker imports; this module imports the job itself, so check the registry's import).
    assert hasattr(core_api.jobs.registry, "outbox_cleanup")
    registry: Any = app.periodic_registry  # Procrastinate leaves its task types unparametrised
    assert registry.periodic_tasks[(OUTBOX_CLEANUP, OUTBOX_CLEANUP)].cron == "30 * * * *"


def test_job_health_counts_rows_unsent_for_over_5_minutes(engine: Engine) -> None:
    # Red when: a stuck relay goes unnoticed (plan Y8), or a row enqueued a moment ago or one
    # already sent is counted.
    add(engine, occurred_at=NOW - timedelta(minutes=6), sent_at=None)
    add(engine, occurred_at=NOW - timedelta(minutes=4), sent_at=None)
    add(engine, occurred_at=NOW - timedelta(hours=1), sent_at=NOW - timedelta(minutes=59))
    with Session(engine) as session:
        health = job_health(session, NOW)
    assert health.outbox_unsent_stale == 1
    assert health.needs_a_look


def test_stale_outbox_is_logged_as_error(engine: Engine, log_output: Callable[[], str]) -> None:
    # Red when: the count is computed but not logged, or logged below ERROR, so the deploy's
    # alert (T0.13) never fires.
    add(engine, occurred_at=NOW - timedelta(minutes=10), sent_at=None)
    report_job_health(engine, NOW)
    [line] = [json.loads(line) for line in log_output().splitlines() if "job queue" in line]
    assert (line["level"], line["outbox_unsent_stale"]) == ("ERROR", 1)
