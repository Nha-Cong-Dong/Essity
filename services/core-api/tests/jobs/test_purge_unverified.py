"""T1.9: accounts never verified are deleted outright after 7 days (ADR-0020 §4).

Rules under test, each named in its test: ADR-0020 §4 (older than 7 days and unverified → gone
with everything that hangs off it; younger or verified → kept), ADR-0018 and A12 (hourly
`@app.periodic` job, never enqueued by hand), A12 (the log line carries the count, no email),
A18 (the job runs through the worker with the `timestamp` Procrastinate passes).
"""

import io
import json
import logging
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

from core_api.db.models import AuthSession, EmailToken, User
from core_api.domain.auth.tokens import TokenPurpose
from core_api.jobs.app import app, deferrer
from core_api.jobs.handler import UnknownJobKind
from core_api.jobs.purge_unverified import (
    PURGE_UNVERIFIED,
    UNVERIFIED_LIFETIME,
    purge_unverified,
)
from core_api.jobs.queue import enqueue_job
from core_api.logging import configure_logging
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.email_token import EmailTokenRepository
from core_api.repositories.user import UserRepository

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def new_user(session: Session, *, age: timedelta, verified: bool) -> User:
    user = UserRepository(session).create(f"purge-{uuid.uuid4().hex[:12]}@example.com")
    user.created_at = NOW - age
    if verified:
        user.email_verified_at = user.created_at
    session.flush()
    return user


def exists(session: Session, user_id: uuid.UUID) -> bool:
    session.expire_all()
    return session.get(User, user_id) is not None


# --- What is deleted (ADR-0020 §4) ------------------------------------------------------------


def test_purge_deletes_unverified_older_than_7_days_and_cascades(db_session: Session) -> None:
    user = new_user(db_session, age=UNVERIFIED_LIFETIME + timedelta(minutes=1), verified=False)
    EmailTokenRepository(db_session).issue(user.id, TokenPurpose.VERIFY_EMAIL, NOW)
    AuthSessionRepository(db_session).create(user.id, NOW)
    db_session.flush()
    user_id = user.id

    assert purge_unverified(db_session, NOW) >= 1
    assert not exists(db_session, user_id)
    for table in (EmailToken, AuthSession):
        assert db_session.scalars(select(table).where(table.user_id == user_id)).all() == []


def test_purge_keeps_unverified_younger_than_7_days(db_session: Session) -> None:
    user = new_user(db_session, age=UNVERIFIED_LIFETIME - timedelta(minutes=1), verified=False)
    purge_unverified(db_session, NOW)
    assert exists(db_session, user.id)


def test_purge_never_touches_verified_accounts(db_session: Session) -> None:
    user = new_user(db_session, age=timedelta(days=400), verified=True)
    purge_unverified(db_session, NOW)
    assert exists(db_session, user.id)


# --- How it runs (ADR-0018, A12, A18) ---------------------------------------------------------


def test_purge_is_registered_as_hourly_periodic() -> None:
    registry: Any = app.periodic_registry  # Procrastinate leaves its task types unparametrised
    assert registry.periodic_tasks[(PURGE_UNVERIFIED, PURGE_UNVERIFIED)].cron == "0 * * * *"


def test_purge_cannot_be_enqueued_by_hand(db_session: Session) -> None:
    """Its task takes Procrastinate's `timestamp`, not a payload: a hand-made job would fail."""
    with pytest.raises(UnknownJobKind):
        enqueue_job(db_session, PURGE_UNVERIFIED, {})


@pytest.fixture
def log_output() -> Iterator[Callable[[], str]]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("core-worker", "INFO", stream=buffer)
    yield buffer.getvalue
    root.handlers, root.level = saved


@pytest.fixture
def old_unverified_committed(engine: Engine) -> Iterator[User]:
    with Session(engine, expire_on_commit=False) as session:
        user = UserRepository(session).create(f"purge-{uuid.uuid4().hex[:12]}@example.com")
        user.created_at = datetime.now(UTC) - UNVERIFIED_LIFETIME - timedelta(hours=1)
        session.commit()
    yield user
    with Session(engine) as session:
        session.execute(delete(User).where(User.id == user.id))
        session.commit()


@pytest.mark.usefixtures("clean_jobs")
def test_purge_runs_in_the_worker_and_logs_only_the_count(
    engine: Engine,
    work: Callable[..., None],
    old_unverified_committed: User,
    log_output: Callable[[], str],
) -> None:
    with engine.begin() as connection:
        raw = connection.connection.driver_connection
        deferrer.configure_task(name=PURGE_UNVERIFIED, connection=raw).defer(timestamp=0)

    work()

    with engine.connect() as connection:
        status = connection.execute(text("SELECT status::text FROM procrastinate_jobs")).scalar()
    assert status == "succeeded"
    with Session(engine) as session:
        assert session.get(User, old_unverified_committed.id) is None
    output = log_output()
    [line] = [
        json.loads(line)
        for line in output.splitlines()
        if line.startswith("{") and "deleted_count" in line
    ]
    assert isinstance(line["deleted_count"], int) and line["deleted_count"] >= 1
    assert old_unverified_committed.email not in output
