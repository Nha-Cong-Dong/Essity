"""The consumer of ai → core events (T4.4, ADR-0006): `python -m core_api.messaging.consumer`.

It reads `events.ai` in the consumer group `core-api` and, for each entry:

1. validates the envelope; an entry that is not a valid event, or of a type with no handler, goes
   to the dead letter stream at once: retrying cannot fix it;
2. in one transaction, claims the event (`idempotency.claim`) and runs its handler, then commits;
   an event already claimed is skipped, so a redelivered event is handled once;
3. acknowledges the entry (`XACK`) after the commit. A crash before the ack redelivers it, and the
   claim makes that harmless.

A handler that fails leaves its entry pending: after `MIN_IDLE_MS` any consumer of the group
takes it back (`XAUTOCLAIM`) and tries again. On its `MAX_DELIVERIES`-th delivery a failing entry
goes to the dead letter stream instead (plan E9).

Handlers are added by the tasks that handle each event (T4.8 on); `HANDLERS` is empty until then,
so there is no Compose service yet: a consumer without handlers would dead-letter every event.
Logs hold ids, counts and class names, never an event (ADR-0013). Not shared with ai-service's
consumer by import (ADR-0003, PLAN T4.4).
"""

import logging
import signal
import socket
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import ResponseError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core_api.messaging.dead_letter import (
    DEAD_STREAM,
    INVALID_ENVELOPE,
    MAX_DELIVERIES_REACHED,
    UNKNOWN_TYPE,
    dead_letter_and_ack,
)
from core_api.messaging.envelope import Event, parse_event
from core_api.messaging.idempotency import claim

SERVICE = "core-consumer"
STREAM = "events.ai"
GROUP = "core-api"
# Plan E9: as many tries as a job gets (MAX_ATTEMPTS); a failed entry waits a minute between.
MAX_DELIVERIES = 5
MIN_IDLE_MS = 60_000
BLOCK_MS = 1_000
COUNT = 10

Handler = Callable[[Session, Event], None]
# By event type; filled by the tasks that handle each ai → core event (T4.8 on).
HANDLERS: dict[str, Handler] = {}

_log = logging.getLogger("core_api.messaging")
_tracer = trace.get_tracer("core_api.messaging")
_PROPAGATOR = TraceContextTextMapPropagator()
Entry = tuple[bytes, dict[bytes, bytes] | None]


class Consumer:
    """One member of the consumer group `group` on `stream`."""

    def __init__(
        self,
        engine: Engine,
        redis: Redis,
        handlers: dict[str, Handler],
        *,
        stream: str = STREAM,
        group: str = GROUP,
        name: str | None = None,
        dead_stream: str = DEAD_STREAM,
        min_idle_ms: int = MIN_IDLE_MS,
        block_ms: int | None = BLOCK_MS,
        count: int = COUNT,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.engine, self.redis, self.handlers = engine, redis, handlers
        self.stream, self.group, self.dead_stream = stream, group, dead_stream
        # Per container: a consumer that dies leaves its entries to the others.
        self.name = name or socket.gethostname()
        self.min_idle_ms, self.block_ms, self.count = min_idle_ms, block_ms, count
        self.clock = clock

    def ensure_group(self) -> None:
        """Create the group from the start of the stream (plan Y1): events sent before core-api
        first started are read too. A group that already exists is kept."""
        try:
            self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def consume_once(self) -> int:
        """Handle the stale pending entries, then the new ones; return how many were seen."""
        seen = 0
        for entry_id, fields in self._claim_stale():
            seen += 1
            self._handle(entry_id, fields, self._deliveries(entry_id))
        for entry_id, fields in self._read_new():
            seen += 1
            self._handle(entry_id, fields, 1)
        return seen

    def _claim_stale(self) -> list[Entry]:
        """Entries delivered over `min_idle_ms` ago and never acknowledged, now this consumer's."""
        response = self.redis.xautoclaim(
            self.stream, self.group, self.name, self.min_idle_ms, "0-0", count=self.count
        )
        claimed = cast(list[Entry], response[1])
        # Entries trimmed (MAXLEN) while pending: nothing left to handle. Redis 7 drops them from
        # the pending list and names them here; the ack covers servers that leave them in it.
        trimmed = [entry_id for entry_id, fields in claimed if fields is None]
        trimmed += cast(list[bytes], response[2]) if len(response) > 2 else []
        if trimmed:
            self.redis.xack(self.stream, self.group, *trimmed)
        return [(entry_id, fields) for entry_id, fields in claimed if fields is not None]

    def _deliveries(self, entry_id: bytes) -> int:
        """How many times the entry has been delivered, this claim included."""
        [info] = cast(
            list[dict[str, Any]],
            self.redis.xpending_range(self.stream, self.group, entry_id, entry_id, 1),
        )
        return int(info["times_delivered"])

    def _read_new(self) -> list[Entry]:
        response = cast(
            list[tuple[bytes, list[Entry]]] | None,
            self.redis.xreadgroup(
                self.group, self.name, {self.stream: ">"}, count=self.count, block=self.block_ms
            ),
        )
        return [entry for _, entries in response or [] for entry in entries]

    def _handle(self, entry_id: bytes, fields: dict[bytes, bytes] | None, deliveries: int) -> None:
        raw = (fields or {}).get(b"envelope")
        if deliveries > MAX_DELIVERIES:
            # Delivered too often without a handler error: its handling kills the process.
            self._dead(entry_id, raw, MAX_DELIVERIES_REACHED, deliveries)
            return
        try:
            event = parse_event(raw if raw is not None else b"")
        except ValidationError:
            self._dead(entry_id, raw, INVALID_ENVELOPE, deliveries)
            return
        handler = self.handlers.get(event.event_type)
        if handler is None:
            self._dead(entry_id, raw, UNKNOWN_TYPE, deliveries, event)
            return
        with _tracer.start_as_current_span(
            f"consume {event.event_type}",
            context=_PROPAGATOR.extract(event.trace_context.model_dump(exclude_none=True)),
            kind=SpanKind.CONSUMER,
            attributes={
                "messaging.system": "redis",
                "messaging.destination.name": self.stream,
                "messaging.message.id": str(event.event_id),
            },
        ) as span:
            try:
                with Session(self.engine) as session, session.begin():
                    now = self.clock()
                    if claim(session, consumer=self.group, event_id=event.event_id, now=now):
                        handler(session, event)
            except Exception as error:
                # Not record_exception: its message may hold data (ADR-0013).
                span.set_status(StatusCode.ERROR)
                _log.warning(
                    "event handler failed",
                    extra={
                        "event_id": str(event.event_id),
                        "event_type": event.event_type,
                        "error_type": type(error).__name__,
                        "deliveries": deliveries,
                    },
                )
                if deliveries >= MAX_DELIVERIES:
                    self._dead(entry_id, raw, type(error).__name__, deliveries, event)
                return
        self.redis.xack(self.stream, self.group, entry_id)

    def _dead(
        self,
        entry_id: bytes,
        raw: bytes | None,
        reason: str,
        deliveries: int,
        event: Event | None = None,
    ) -> None:
        dead_letter_and_ack(
            self.redis,
            stream=self.stream,
            group=self.group,
            entry_id=entry_id,
            envelope=raw if raw is not None else b"",
            reason=reason,
            deliveries=deliveries,
            dead_stream=self.dead_stream,
        )
        extra: dict[str, object] = {"reason": reason, "deliveries": deliveries}
        if event is not None:
            extra |= {"event_id": str(event.event_id), "event_type": event.event_type}
        _log.error("event dead-lettered", extra=extra)


def run(consumer: Consumer, stop: threading.Event, *, pause_seconds: float = 1.0) -> None:
    """Consume until `stop` is set; each read blocks for at most `block_ms`."""
    consumer.ensure_group()
    while not stop.is_set():
        try:
            consumer.consume_once()
        except Exception:  # Redis or the database is down, say: log it and try again
            _log.exception("event consumer round failed")
            stop.wait(pause_seconds)


def install_signal_handlers(stop: threading.Event) -> None:
    """SIGTERM (docker stop) and SIGINT end the loop after the current round."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda signum, frame: stop.set())


def main() -> None:
    from core_api.clients.redis import redis_from_url
    from core_api.config import get_settings
    from core_api.db.engine import get_engine
    from core_api.logging import configure_logging
    from core_api.telemetry import configure_tracing

    settings = get_settings()
    configure_logging(SERVICE, settings.log_level)
    provider = configure_tracing(SERVICE)
    # A blocking read must end before the socket times out.
    redis = redis_from_url(settings.redis_url.get_secret_value(), timeout=BLOCK_MS / 1000 + 4)
    stop = threading.Event()
    install_signal_handlers(stop)
    _log.info("consumer starting")
    try:
        run(Consumer(get_engine(), redis, HANDLERS), stop)
    finally:
        provider.shutdown()
        _log.info("consumer stopped")


if __name__ == "__main__":
    main()
