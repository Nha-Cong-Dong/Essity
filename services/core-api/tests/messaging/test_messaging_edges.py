"""Edge cases of the outbox, relay, idempotency and consumer found by the feature tester's
mutation run (T4.2, T4.4): two claims at once, the relay loop after a full batch, the 7-day
boundary of the cleanup, a stale row that is backing off, the dead letter keeping every entry in
one MULTI, the user context after a round, and an optional object key. Real PostgreSQL and Redis.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import Engine, text, update
from sqlalchemy.orm import Session

from core_api.db.models import Outbox
from core_api.jobs.job_health import job_health
from core_api.jobs.outbox_cleanup import SENT_KEPT_FOR, delete_sent_outbox
from core_api.logging import user_id_var
from core_api.messaging.consumer import (
    Consumer,
    Handler,
    _object_keys,  # pyright: ignore[reportPrivateUsage]
)
from core_api.messaging.envelope import (
    Event,
    ObjectKey,
    SessionProgress,
    SessionProgressEvent,
    UserDeleted,
    dump_event,
)
from core_api.messaging.idempotency import claim
from core_api.messaging.outbox import enqueue_event
from core_api.messaging.relay import BATCH, run
from races import finished, in_thread, wait_for_lock

pytestmark = pytest.mark.usefixtures("clean_outbox")

NOW = datetime(2026, 10, 26, 8, 30, tzinfo=UTC)


# --- Two consumers claiming the same event at once ----------------------------------------


def _race_claim(engine: Engine, *, first_commits: bool) -> object:
    """Session A claims and holds its transaction; session B claims the same event meanwhile.
    Return what B's claim gave once A committed or rolled back."""
    event_id = uuid.uuid4()
    with Session(engine) as first:
        assert claim(first, consumer="core-api", event_id=event_id, now=NOW) is True
        second = Session(engine)
        try:
            pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()

            thread, outcome = in_thread(
                lambda: claim(second, consumer="core-api", event_id=event_id, now=NOW)
            )
            wait_for_lock(engine, pid, outcome)
            if first_commits:
                first.commit()
            else:
                first.rollback()
            result = finished(thread, outcome)
            second.rollback()
        finally:
            second.close()
    return result


def test_concurrent_claim_waits_and_loses_to_a_commit(engine: Engine) -> None:
    # Red when: claim checks first and inserts after (SELECT then INSERT): both transactions see
    # no row, and the second fails with a unique violation instead of returning False, so a
    # redelivery that overlaps the first handling is counted as a handler failure.
    assert _race_claim(engine, first_commits=True) is False


def test_concurrent_claim_wins_after_the_first_rolls_back(engine: Engine) -> None:
    # Red when: a claim that lost the race is not retried by the database after the holder
    # rolled back (the event would be skipped although nobody handled it).
    assert _race_claim(engine, first_commits=False) is True


# --- The relay loop -------------------------------------------------------------------------


class _Stop:
    """A stop signal that records how long each wait asked for."""

    def __init__(self) -> None:
        self.waits: list[float] = []
        self.stopped = False

    def is_set(self) -> bool:
        return self.stopped

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(timeout or 0.0)
        return self.stopped


def test_relay_loop_goes_again_at_once_after_a_full_batch(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: the loop waits a poll after every round, so a backlog (Redis back after an
    # outage) drains at BATCH events a second instead of as fast as Redis takes them.
    stop = _Stop()
    sent = [BATCH, BATCH, 3]

    def relay_once(*args: Any, **kwargs: Any) -> int:
        result = sent.pop(0)
        if not sent:
            stop.stopped = True
        return result

    monkeypatch.setattr("core_api.messaging.relay.relay_once", relay_once)
    run(engine, None, stop, poll_seconds=7)  # pyright: ignore[reportArgumentType]
    assert stop.waits == [7]


# --- Outbox upkeep boundaries ---------------------------------------------------------------


def _add(engine: Engine, *, occurred_at: datetime, **values: Any) -> uuid.UUID:
    with Session(engine) as session:
        event_id = enqueue_event(session, UserDeleted(), user_id=uuid.uuid4(), now=occurred_at)
        session.flush()
        if values:
            session.execute(update(Outbox).where(Outbox.id == event_id).values(**values))
        session.commit()
    return event_id


def test_cleanup_keeps_a_row_sent_exactly_7_days_ago(engine: Engine) -> None:
    # Red when: the cleanup deletes at 7 days (<=) instead of after them: plan E8 keeps sent rows
    # 7 days to look into a problem.
    kept = _add(engine, occurred_at=NOW - timedelta(days=8), sent_at=NOW - SENT_KEPT_FOR)
    with Session(engine) as session:
        assert delete_sent_outbox(session, NOW) == 0
        session.commit()
        assert session.get(Outbox, kept) is not None


def test_stale_count_includes_a_row_that_is_backing_off(engine: Engine) -> None:
    # Red when: job_health counts by available_at: a row whose send keeps failing pushes its
    # available_at forward every try (retry_delay), so the stuck event is never reported
    # although it was due 10 minutes ago (plan Y8: "unsent 5 minutes after the event").
    _add(
        engine,
        occurred_at=NOW - timedelta(minutes=10),
        attempts=12,
        available_at=NOW + timedelta(seconds=20),
        last_error="ConnectionError",
    )
    with Session(engine) as session:
        assert job_health(session, NOW).outbox_unsent_stale == 1


# --- The consumer ---------------------------------------------------------------------------


@pytest.fixture
def make_consumer(
    engine: Engine, redis_client: Redis, stream: str
) -> Iterator[tuple[Any, str, str]]:
    dead = f"{stream}.dead"

    def make(handlers: dict[str, Handler]) -> Consumer:
        consumer = Consumer(
            engine,
            redis_client,
            handlers,
            stream=stream,
            dead_stream=dead,
            name="edge-consumer",
            min_idle_ms=0,
            block_ms=None,
            clock=lambda: NOW,
        )
        consumer.ensure_group()
        return consumer

    yield make, stream, dead
    redis_client.delete(stream, dead)


def _progress() -> SessionProgressEvent:
    return SessionProgressEvent.model_validate(
        {
            "event_id": uuid.uuid4(),
            "event_type": "session.progress.v1",
            "schema_version": 1,
            "occurred_at": NOW,
            "user_id": uuid.uuid4(),
            "trace_context": {},
            "payload": SessionProgress(
                study_session_id=uuid.uuid4(), run_id=uuid.uuid4(), step="anchoring", percent=40
            ),
        }
    )


def test_user_context_is_cleared_after_the_last_entry_of_a_round(
    make_consumer: tuple[Any, str, str], redis_client: Redis
) -> None:
    # Red when: user_id_var is not reset after an entry. The existing leak test ends its round on
    # a poison entry, which sets the user to None anyway; with a valid event last, the user would
    # stay on every log line the loop writes next ("event consumer round failed", say).
    make, source, _ = make_consumer

    def noop(session: Session, event: Event) -> None:
        pass

    consumer = make({"session.progress.v1": noop})
    redis_client.xadd(source, {"envelope": dump_event(_progress())})
    assert consumer.consume_once() == ["processed"]
    assert user_id_var.get() is None


def test_dead_letter_keeps_every_entry(
    make_consumer: tuple[Any, str, str], redis_client: Redis
) -> None:
    # Red when: the dead letter stream is trimmed (plan G4: no MAXLEN; nothing there may go
    # before someone looked at it).
    make, source, dead = make_consumer
    consumer = make({})
    for index in range(3):
        redis_client.xadd(source, {"envelope": f"poison {index}"})
    assert consumer.consume_once() == ["dead"] * 3
    assert redis_client.xlen(dead) == 3


def test_dead_letter_copy_and_ack_run_in_one_multi(
    make_consumer: tuple[Any, str, str], redis_client: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: the copy to events.dead and the XACK are sent as a plain pipeline: a connection
    # lost between them acks an entry that never reached the dead letter (lost), the docstring's
    # "both or neither" no longer holds.
    make, source, dead = make_consumer
    consumer = make({})
    modes: list[bool] = []
    real: Any = redis_client.pipeline  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    def pipeline(transaction: bool = True, shard_hint: Any = None) -> Any:
        modes.append(transaction)
        return real(transaction=transaction, shard_hint=shard_hint)

    monkeypatch.setattr(redis_client, "pipeline", pipeline)
    redis_client.xadd(source, {"envelope": "poison"})
    assert consumer.consume_once() == ["dead"]
    assert modes == [True]
    assert redis_client.xlen(dead) == 1


class _OptionalKey(BaseModel):
    key: ObjectKey | None = None


def test_an_optional_object_key_is_found() -> None:
    # Red when: _object_keys does not look inside Optional/Union annotations. No contract field
    # is an optional key today, so no event test can see it; the first one added (say
    # `toc_key: ObjectKey | None`) would skip the F2 check silently.
    key = f"users/{uuid.uuid4()}/subjects/s/a.pdf"
    assert list(_object_keys(_OptionalKey(key=key), None)) == [key]
    assert list(_object_keys(_OptionalKey(), None)) == []
