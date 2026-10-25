"""The outbox relay: `python -m core_api.messaging.relay` (Compose service `core-relay`, T4.2).

Every second it takes the due, unsent rows of `outbox`, oldest first, and in one transaction:

1. `SELECT … FOR UPDATE SKIP LOCKED`: two relays share the work and never take the same row;
2. `XADD` each event to `events.core` (one pipeline);
3. marks the rows sent and commits.

A relay that dies between 2 and 3 leaves the rows unsent, so they go out again: delivery is at
least once, and consumers skip an `event_id` they have already handled (ADR-0006). When Redis
fails, the same transaction pushes the rows back (`retry_delay`) and records the error's class
name; a row is never dropped. A row that no longer passes the contract is held back the same
way, alone, so it cannot stop the rows behind it.

A separate process rather than a Procrastinate job (plan E1): a periodic job runs at most once a
minute, and US-02 AC11 gives the whole pipeline 3 minutes.

Logs hold counts and class names only, never an event (ADR-0013).
"""

import logging
import signal
import threading
from datetime import UTC, datetime, timedelta

from pydantic import TypeAdapter, ValidationError
from redis import Redis
from redis.exceptions import RedisError
from redis.typing import EncodableT, FieldT
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from core_api.db.models import Outbox
from core_api.messaging.envelope import Event, dump_event

SERVICE = "core-relay"
STREAM = "events.core"
# Trimmed approximately: entries every consumer has read are history, not a queue (plan E3).
STREAM_MAXLEN = 100_000
BATCH = 100
POLL_SECONDS = 1.0
MAX_DELAY = timedelta(seconds=30)

_log = logging.getLogger("core_api.messaging")
_EVENT: TypeAdapter[Event] = TypeAdapter(Event)


def retry_delay(attempts: int) -> timedelta:
    """How long a row waits after its `attempts`-th failed send: 2, 4, 8, 16, then 30 s."""
    return min(timedelta(seconds=2 ** min(attempts, 5)), MAX_DELAY)


def envelope_of(row: Outbox) -> str:
    """The event of `row`, as it travels, validated against the contract again."""
    event = _EVENT.validate_python(
        {
            "event_id": row.id,
            "event_type": row.event_type,
            "schema_version": 1,
            "occurred_at": row.occurred_at.astimezone(UTC),
            "user_id": row.user_id,
            "trace_context": row.trace_context,
            "payload": row.payload,
        }
    )
    return dump_event(event)


def relay_once(
    engine: Engine,
    redis: Redis,
    *,
    now: datetime | None = None,
    stream: str = STREAM,
    batch: int = BATCH,
) -> int:
    """Send up to `batch` due rows; return how many were sent (0 when Redis failed)."""
    now = now or datetime.now(UTC)
    with Session(engine) as session, session.begin():
        rows = session.scalars(
            select(Outbox)
            .where(Outbox.sent_at.is_(None), Outbox.available_at <= now)
            .order_by(Outbox.seq)
            .limit(batch)
            .with_for_update(skip_locked=True)
        ).all()
        if not rows:
            return 0
        # A row that no longer validates waits like a failed send instead of failing the batch.
        ready: list[tuple[Outbox, str]] = []
        for row in rows:
            try:
                ready.append((row, envelope_of(row)))
            except ValidationError as error:
                _hold_back([row], error, now)
        if not ready:
            return 0
        try:
            # redis-py leaves Pipeline's type parameter unknown.
            pipeline = redis.pipeline(transaction=False)  # pyright: ignore[reportUnknownMemberType]
            for _, envelope in ready:
                fields: dict[FieldT, EncodableT] = {"envelope": envelope}
                pipeline.xadd(stream, fields, maxlen=STREAM_MAXLEN, approximate=True)
            pipeline.execute()
        except RedisError as error:
            _hold_back([row for row, _ in ready], error, now)
            return 0
        for row, _ in ready:
            row.sent_at = now
    _log.info("outbox relayed", extra={"event_count": len(ready)})
    return len(ready)


def _hold_back(rows: list[Outbox], error: Exception, now: datetime) -> None:
    """Count a failed send of `rows` and push them back; never drop them."""
    for row in rows:
        row.attempts += 1
        row.available_at = now + retry_delay(row.attempts)
        row.last_error = type(error).__name__
    _log.warning(
        "outbox send failed",
        extra={"event_count": len(rows), "error_type": type(error).__name__},
    )


def run(
    engine: Engine,
    redis: Redis,
    stop: threading.Event,
    *,
    stream: str = STREAM,
    poll_seconds: float = POLL_SECONDS,
) -> None:
    """Relay until `stop` is set: at once while full batches keep coming, else every poll."""
    while not stop.is_set():
        try:
            sent = relay_once(engine, redis, stream=stream)
        except Exception:  # the database is down, say: log it and try again next round
            _log.exception("outbox relay round failed")
            sent = 0
        if sent < BATCH:
            stop.wait(poll_seconds)


def install_signal_handlers(stop: threading.Event) -> None:
    """SIGTERM (docker stop) and SIGINT end the loop after the current round."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda signum, frame: stop.set())


def main() -> None:
    from core_api.clients.redis import get_redis
    from core_api.config import get_settings
    from core_api.db.engine import get_engine
    from core_api.logging import configure_logging
    from core_api.telemetry import configure_tracing

    configure_logging(SERVICE, get_settings().log_level)
    provider = configure_tracing(SERVICE)
    stop = threading.Event()
    install_signal_handlers(stop)
    _log.info("relay starting")
    try:
        run(get_engine(), get_redis(), stop)
    finally:
        provider.shutdown()
        _log.info("relay stopped")


if __name__ == "__main__":
    main()
