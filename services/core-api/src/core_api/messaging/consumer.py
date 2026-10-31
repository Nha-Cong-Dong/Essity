"""The consumer of ai → core events (T4.4, ADR-0006): `python -m core_api.messaging.consumer`.

It reads `events.ai` in the consumer group `core-api` and, for each entry:

1. validates the envelope; an entry that can never succeed goes to the dead letter stream at
   once, because retrying cannot fix it: not an envelope, a type outside the contract, a known
   type with no handler yet, or an object key of another user than the envelope's (F2);
2. in one transaction, claims the event (`idempotency.claim`) and runs its handler, then commits;
   an event already claimed is skipped, so a redelivered event is handled once;
3. acknowledges the entry (`XACK`) after the commit. A crash before the ack redelivers it, and the
   claim makes that harmless.

A handler that fails leaves its entry pending, due again after a backoff (5, 15, 45, then 60 s,
set with `XCLAIM IDLE`): any consumer of the group takes it back (`XAUTOCLAIM`) and tries again.
On its `MAX_DELIVERIES`-th delivery a failing entry goes to the dead letter stream instead (plan
E9). A lost connection (the database or Redis down) is not a failure of the event: the entry is
put back with its delivery count as it was (`is_outage`), so downtime does not use up deliveries.

Handlers are added by the tasks that handle each event (T4.8 on); `HANDLERS` holds the ones that
need nothing but the database (the document ones), `build_handlers` adds those that read files
(`grade.completed.v1`, T4.19). There is no Compose service until every event has a handler: the
others would be dead-lettered.
Logs hold ids, counts and class names, never an event (ADR-0013). Not shared with ai-service's
consumer by import (ADR-0003, PLAN T4.4).
"""

import json
import logging
import signal
import socket
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from types import UnionType
from typing import Annotated, Any, Protocol, Union, cast, get_args, get_origin

from opentelemetry import trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from pydantic import BaseModel, StringConstraints, ValidationError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.orm import Session

from core_api.handlers.document_indexed import on_document_failed, on_document_indexed
from core_api.handlers.session_progress import on_session_failed, on_session_progress
from core_api.logging import user_id_var
from core_api.messaging.dead_letter import (
    DEAD_STREAM,
    INVALID_ENVELOPE,
    MAX_DELIVERIES_REACHED,
    NO_HANDLER,
    UNKNOWN_TYPE,
    USER_MISMATCH,
    dead_letter_and_ack,
)
from core_api.messaging.envelope import OBJECT_KEY_PATTERN, Event, parse_event
from core_api.messaging.idempotency import claim, was_processed

SERVICE = "core-consumer"
STREAM = "events.ai"
GROUP = "core-api"
# Plan E9: as many tries as a job gets (MAX_ATTEMPTS). An entry read and not acknowledged for
# MIN_IDLE_MS is taken back; a failed one waits BACKOFF_BASE_MS * 3^(n-1), at most MIN_IDLE_MS.
MAX_DELIVERIES = 5
MIN_IDLE_MS = 60_000
BACKOFF_BASE_MS = 5_000
BLOCK_MS = 1_000
COUNT = 10
# The loop's own pause after rounds that failed, doubling up to the cap.
PAUSE_S = 1.0
MAX_PAUSE_S = 30.0
# Fixed: the stream is known, and an event type is only trusted after parsing.
SPAN_NAME = "events.ai process"

Handler = Callable[[Session, Event], None]
# By event type; filled by the tasks that handle each ai → core event (T4.8 on).
HANDLERS: dict[str, Handler] = {
    "document.indexed.v1": on_document_indexed,
    "document.failed.v1": on_document_failed,
    "session.progress.v1": on_session_progress,
    "session.failed.v1": on_session_failed,
}


def build_handlers() -> dict[str, Handler]:
    """Every handler of this process: `HANDLERS` and the ones that read the object storage."""
    from core_api.clients.storage import S3Storage
    from core_api.config import get_settings
    from core_api.handlers.document_indexed import OnDocumentIndexed
    from core_api.handlers.grade_completed import OnGradeCompleted
    from core_api.handlers.session_processed import OnSessionProcessed

    settings = get_settings()
    storage = S3Storage.from_settings(settings)
    return HANDLERS | {
        "document.indexed.v1": OnDocumentIndexed(storage),
        "grade.completed.v1": OnGradeCompleted(storage, environment=settings.environment),
        "session.processed.v1": OnSessionProcessed(storage),
    }


# Every event_type in the contract, to tell an unknown type from a malformed known one.
EVENT_TYPES = frozenset(
    get_args(model.model_fields["event_type"].annotation)[0]
    for model in get_args(get_args(Event)[0])
)

# SQLSTATEs of a lost or refused connection: class 08 (connection exception), and the server
# shutting down or starting up (57P01-57P03).
_OUTAGE_SQLSTATE_CLASS = "08"
_OUTAGE_SQLSTATES = frozenset({"57P01", "57P02", "57P03"})
# Outcomes that mark the span as an error.
_FAILED = frozenset({"retry", "unavailable", "dead"})

_log = logging.getLogger("core_api.messaging")
_tracer = trace.get_tracer("core_api.messaging")
_PROPAGATOR = TraceContextTextMapPropagator()
Entry = tuple[bytes, dict[bytes, bytes] | None]


def is_outage(error: BaseException) -> bool:
    """Whether `error` means the database or Redis is unreachable, not that the work failed.

    Only a lost connection counts: psycopg raises OperationalError for a statement timeout, a
    deadlock or a full disk too, and those fail the same way every time, so they go towards the
    dead letter. No SQLSTATE means the error came from the client side (could not connect,
    socket closed).
    """
    if isinstance(error, RedisConnectionError | RedisTimeoutError):
        return True
    if not isinstance(error, DBAPIError):
        return False
    if error.connection_invalidated:
        return True
    if not isinstance(error, OperationalError | InterfaceError):
        return False
    sqlstate = getattr(error.orig, "sqlstate", None)
    return (
        sqlstate is None
        or sqlstate.startswith(_OUTAGE_SQLSTATE_CLASS)
        or sqlstate in _OUTAGE_SQLSTATES
    )


def backoff_ms(failures: int, *, base_ms: int, cap_ms: int) -> int:
    """How long an entry waits after its `failures`-th failed delivery: 5, 15, 45, 60 s."""
    return min(base_ms * 3 ** (failures - 1), cap_ms)


def keys_belong_to_user(event: Event) -> bool:
    """F2: every object key in the payload is under `users/<event.user_id>/`.

    Found by type (the contract's ObjectKey), through lists, optionals and nested models, not by
    field name: a key added to the contract under any name is checked too.
    """
    owner = f"users/{event.user_id}/"
    return all(key.startswith(owner) for key in _object_keys(event.payload, None))


def _object_keys(value: Any, annotation: Any) -> Iterator[str]:
    if value is None:
        return
    if isinstance(value, BaseModel):
        for name, info in type(value).model_fields.items():
            field_type = (
                Annotated[info.annotation, *info.metadata] if info.metadata else info.annotation
            )
            yield from _object_keys(getattr(value, name), field_type)
        return
    origin = get_origin(annotation)
    if origin is Annotated:
        base, *metadata = get_args(annotation)
        if isinstance(value, str) and any(_is_object_key(item) for item in metadata):
            yield value
            return
        yield from _object_keys(value, base)
    elif origin in (Union, UnionType):
        for option in get_args(annotation):
            yield from _object_keys(value, option)
    elif isinstance(value, list | tuple):
        item_type = get_args(annotation)[0] if get_args(annotation) else None
        for item in cast(list[Any], value):
            yield from _object_keys(item, item_type)


def _is_object_key(metadata: Any) -> bool:
    return isinstance(metadata, StringConstraints) and metadata.pattern == OBJECT_KEY_PATTERN


def _rejection_reason(raw: bytes) -> str:
    """`unknown_type` for a well-formed event of a type outside the contract, else invalid."""
    try:
        data = json.loads(raw)
    except ValueError:
        return INVALID_ENVELOPE
    if isinstance(data, dict):
        event_type = cast(dict[str, Any], data).get("event_type")
        if isinstance(event_type, str) and event_type not in EVENT_TYPES:
            return UNKNOWN_TYPE
    return INVALID_ENVELOPE


@dataclass(frozen=True)
class _Result:
    outcome: str  # processed | duplicate | unavailable | retry | dead


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
        backoff_base_ms: int = BACKOFF_BASE_MS,
        block_ms: int | None = BLOCK_MS,
        count: int = COUNT,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.engine, self.redis, self.handlers = engine, redis, handlers
        self.stream, self.group, self.dead_stream = stream, group, dead_stream
        # Per container: a consumer that dies leaves its entries to the others.
        self.name = name or socket.gethostname()
        self.min_idle_ms, self.backoff_base_ms = min_idle_ms, backoff_base_ms
        self.block_ms, self.count = block_ms, count
        self.clock = clock
        self._cursor = "0-0"

    def ensure_group(self) -> None:
        """Create the group from the start of the stream (plan Y1): events sent before core-api
        first started are read too. A group that already exists is kept."""
        try:
            self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def consume_once(self) -> list[str]:
        """Handle the stale pending entries, then the new ones; return each one's outcome."""
        outcomes = [
            self._handle(entry_id, fields, self._deliveries(entry_id))
            for entry_id, fields in self._claim_stale()
        ]
        # Nothing to wait for while entries due again keep coming: read at once.
        block = None if outcomes else self.block_ms
        outcomes += [
            self._handle(entry_id, fields, 1) for entry_id, fields in self._read_new(block)
        ]
        return outcomes

    def _claim_stale(self) -> list[Entry]:
        """Entries due again (idle over `min_idle_ms`, never acknowledged), now this consumer's."""
        # Redis is instrumented for the whole process: polling an empty stream every second
        # would be a root trace per round. The entries that are handled have their own span.
        with suppress_instrumentation():
            response = self.redis.xautoclaim(
                self.stream,
                self.group,
                self.name,
                self.min_idle_ms,
                self._cursor,
                count=self.count,
            )
        # Where the next scan starts ("0-0" once it has seen the whole pending list): without
        # it a failing first entry is taken back every round and the ones behind never are.
        self._cursor = response[0].decode() if isinstance(response[0], bytes) else str(response[0])
        claimed = cast(list[Entry], response[1])
        # An entry trimmed (MAXLEN) while pending comes back without fields: Redis 7 and later
        # have already dropped it from the pending list, so there is nothing to handle or ack.
        return [(entry_id, fields) for entry_id, fields in claimed if fields is not None]

    def _deliveries(self, entry_id: bytes) -> int:
        """How many times the entry has been delivered, this claim included."""
        rows = cast(
            list[dict[str, Any]],
            self.redis.xpending_range(self.stream, self.group, entry_id, entry_id, 1),
        )
        return int(rows[0]["times_delivered"]) if rows else 1

    def _read_new(self, block: int | None) -> list[Entry]:
        with suppress_instrumentation():
            response = cast(
                list[tuple[bytes, list[Entry]]] | None,
                self.redis.xreadgroup(
                    self.group, self.name, {self.stream: ">"}, count=self.count, block=block
                ),
            )
        return [entry for _, entries in response or [] for entry in entries]

    def _handle(self, entry_id: bytes, fields: dict[bytes, bytes] | None, deliveries: int) -> str:
        """Handle one entry delivered `deliveries` times; return its outcome.

        One span per entry, continuing the trace the envelope carries. The span and the log lines
        hold ids, counts, the outcome and class names only (ADR-0013), `event_id` and
        `event_type` only once the envelope has passed the contract.
        """
        raw = (fields or {}).get(b"envelope")
        event: Event | None = None
        rejected = INVALID_ENVELOPE
        if raw is not None:
            try:
                event = parse_event(raw)
            except ValidationError:
                rejected = _rejection_reason(raw)
        carrier = event.trace_context.model_dump(exclude_none=True) if event else {}
        # Reset after the entry: the loop is one context, and the next entry's log lines must
        # not carry this user.
        user_token = user_id_var.set(str(event.user_id) if event else None)
        try:
            with _tracer.start_as_current_span(
                SPAN_NAME,
                context=_PROPAGATOR.extract(carrier),
                kind=SpanKind.CONSUMER,
                record_exception=False,
                set_status_on_exception=False,
                attributes={"messaging.system": "redis", "messaging.destination.name": self.stream},
            ) as span:
                span.set_attribute("deliveries", deliveries)
                if event is not None:
                    span.set_attribute("event_id", str(event.event_id))
                    span.set_attribute("event_type", event.event_type)
                result = self._process(entry_id, raw, event, rejected, deliveries)
                span.set_attribute("outcome", result.outcome)
                if result.outcome in _FAILED:
                    # No description: an exception's message may hold data (ADR-0013).
                    span.set_status(StatusCode.ERROR)
                return result.outcome
        finally:
            user_id_var.reset(user_token)

    def _process(
        self,
        entry_id: bytes,
        raw: bytes | None,
        event: Event | None,
        rejected: str,
        deliveries: int,
    ) -> _Result:
        if event is None:
            return self._dead(entry_id, raw, rejected, deliveries)
        if not keys_belong_to_user(event):
            return self._dead(entry_id, raw, USER_MISMATCH, deliveries, event)
        handler = self.handlers.get(event.event_type)
        if handler is None:
            return self._dead(entry_id, raw, NO_HANDLER, deliveries, event)
        if deliveries > MAX_DELIVERIES:
            return self._over_delivered(entry_id, raw, event, deliveries)
        try:
            with Session(self.engine) as session, session.begin():
                if claim(session, consumer=self.group, event_id=event.event_id, now=self.clock()):
                    handler(session, event)
                    outcome = "processed"
                else:
                    outcome = "duplicate"
        except Exception as error:
            return self._failed(entry_id, raw, event, deliveries, error)
        self.redis.xack(self.stream, self.group, entry_id)
        return _Result(outcome)

    def _over_delivered(
        self, entry_id: bytes, raw: bytes | None, event: Event, deliveries: int
    ) -> _Result:
        """Delivered more often than allowed without a recorded failure: its handling kills the
        process, or it was handled and only its acknowledgement kept failing."""
        try:
            with Session(self.engine) as session:
                done = was_processed(session, consumer=self.group, event_id=event.event_id)
        except Exception as error:
            if is_outage(error):
                self._put_back(entry_id, deliveries)
                return self._unavailable(event, deliveries, error)
            # Cannot tell, and it would fail the same way every round.
            return self._dead(entry_id, raw, MAX_DELIVERIES_REACHED, deliveries, event)
        if done:
            self.redis.xack(self.stream, self.group, entry_id)
            return _Result("duplicate")
        return self._dead(entry_id, raw, MAX_DELIVERIES_REACHED, deliveries, event)

    def _failed(
        self, entry_id: bytes, raw: bytes | None, event: Event, deliveries: int, error: Exception
    ) -> _Result:
        if is_outage(error):
            self._put_back(entry_id, deliveries)
            return self._unavailable(event, deliveries, error)
        error_type = type(error).__name__
        # Not the exception's message or traceback: they may hold data (ADR-0013).
        _log.warning(
            "event handler failed",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "error_type": error_type,
                "deliveries": deliveries,
            },
        )
        if deliveries >= MAX_DELIVERIES:
            return self._dead(entry_id, raw, error_type, deliveries, event)
        self._back_off(entry_id, deliveries)
        return _Result("retry")

    def _unavailable(self, event: Event, deliveries: int, error: Exception) -> _Result:
        _log.warning(
            "event consumer unavailable",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "error_type": type(error).__name__,
                "deliveries": deliveries,
            },
        )
        return _Result("unavailable")

    def _back_off(self, entry_id: bytes, failures: int) -> None:
        """Make the entry look idle for `min_idle - backoff`: XAUTOCLAIM takes it after backoff.

        JUSTID leaves the delivery count alone. IDLE is clamped at 0: Redis accepts a negative
        one, which would push the entry's due time into the future.
        """
        wait = backoff_ms(failures, base_ms=self.backoff_base_ms, cap_ms=self.min_idle_ms)
        self.redis.xclaim(
            self.stream,
            self.group,
            self.name,
            0,
            [entry_id],
            idle=max(0, self.min_idle_ms - wait),
            justid=True,
        )

    def _put_back(self, entry_id: bytes, deliveries: int) -> None:
        """Keep the entry pending as if this delivery had not happened.

        RETRYCOUNT sets the delivery count back to what it was before this delivery; the idle
        time restarts at 0, so XAUTOCLAIM takes the entry again after `min_idle`.
        """
        self.redis.xclaim(
            self.stream,
            self.group,
            self.name,
            0,
            [entry_id],
            retrycount=deliveries - 1,
            justid=True,
        )

    def _dead(
        self,
        entry_id: bytes,
        raw: bytes | None,
        reason: str,
        deliveries: int,
        event: Event | None = None,
    ) -> _Result:
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
        return _Result("dead")


class StopSignal(Protocol):
    def is_set(self) -> bool: ...
    def wait(self, timeout: float | None = None) -> bool: ...


def pause_s(failures: int) -> float:
    """How long the loop waits after `failures` bad rounds in a row: 1, 2, 4, ... 30 s."""
    return min(PAUSE_S * 2 ** (failures - 1), MAX_PAUSE_S)


def run(consumer: Consumer, stop: StopSignal) -> None:
    """Consume until `stop` is set; each round blocks for at most `block_ms`.

    A round that raises (Redis or the database down, an acknowledgement lost) or that found the
    infrastructure unavailable is logged, and the loop slows down until a round goes well: it
    neither ends the process nor spins against a server that is down.
    """
    grouped = False
    failures = 0
    while not stop.is_set():
        try:
            if not grouped:
                consumer.ensure_group()
                grouped = True
            outcomes = consumer.consume_once()
        except Exception as error:
            # The class name only: a traceback or a SQLAlchemy error carries the statement,
            # its parameters or a message with data (ADR-0013).
            _log.error("event consumer round failed", extra={"error_type": type(error).__name__})
            failures += 1
        else:
            failures = failures + 1 if "unavailable" in outcomes else 0
        if failures:
            stop.wait(pause_s(failures))


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
        run(Consumer(get_engine(), redis, build_handlers()), stop)
    finally:
        provider.shutdown()
        _log.info("consumer stopped")


if __name__ == "__main__":
    main()
