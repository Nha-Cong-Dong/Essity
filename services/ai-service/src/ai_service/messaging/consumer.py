"""The consumer of `events.core` (T4.3, ADR-0006): core-api's events, handled once each.

Delivery is at least once (the relay may resend, a consumer may crash), so every event goes
through the same steps, in this order:

1. claim its `event_id` in `processed_event` and run its handler, in one transaction;
2. COMMIT;
3. XACK.

A crash before 2 leaves nothing behind and the entry is delivered again. A crash between 2 and
3 delivers it again too, and the claim finds it and skips the handler. Entries a consumer
read but never acknowledged are taken back with XAUTOCLAIM once they have been idle
`min_idle_ms`.

When the handler fails, the entry stays pending and comes back after a backoff (5, 15, 45,
then 60 s); on its `max_attempts`-th delivery it goes to the dead letter instead. An entry that
can never succeed goes there at once: one that does not parse, an event type outside the
contract, a known type without a handler yet (replayable once there is one), or an object key
belonging to another user than the envelope's (F2).

Same pattern as core-api's consumer (T4.4) but not shared by import (ADR-0003, PLAN T4.4).
"""

import json
import logging
import signal
import socket
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import UnionType
from typing import Annotated, Any, Protocol, Union, cast, get_args, get_origin

from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from pydantic import BaseModel, StringConstraints, ValidationError
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.orm import Session

from ai_service.logging import user_id_var
from ai_service.messaging.dead_letter import (
    INVALID_ENVELOPE,
    MAX_DELIVERIES,
    NO_HANDLER,
    UNKNOWN_TYPE,
    USER_MISMATCH,
    send_to_dead,
)
from ai_service.messaging.envelope import OBJECT_KEY_PATTERN, Event, parse_event
from ai_service.messaging.idempotency import claim, was_processed

SERVICE = "ai-consumer"
STREAM = "events.core"
# Also the `consumer` column of `processed_event`.
GROUP = "ai-service"
DEAD_STREAM = "events.dead"
# Deliveries of one entry before it goes to the dead letter (plan E9).
MAX_ATTEMPTS = 5
# An entry read and not acknowledged for this long is taken back (plan E9). Must exceed the
# longest handler when several consumers run, or two of them handle the same entry at once
# (the claim then makes the second wait and skip). Also the longest backoff.
MIN_IDLE_MS = 60_000
BACKOFF_BASE_MS = 5_000
BATCH = 10
# A blocking read; the Redis client's socket timeout (5 s) must stay above it.
BLOCK_MS = 1_000
# The loop's own pause after rounds that failed, doubling up to the cap.
PAUSE_S = 1.0
MAX_PAUSE_S = 30.0

Handler = Callable[[Session, Event], None]
"""Handles one event inside the consumer's transaction.

- Writes to the database only through `session`; the consumer commits it with the claim.
- Any other effect (an object written, an event sent) must be idempotent on the event: keyed by
  `event_id` or a run id derived from it, because the event may be handled again after a
  failure.
- Takes the user from `event.user_id`, never from the payload: the consumer has checked that
  every object key in the payload belongs to that user (F2).
"""


class Deferred(Exception):
    """Raised by a handler to put its event back for later, without counting a failure.

    For work that cannot run *now*: the user is over their AI quota (T2.11), or the LLM provider
    answers 5xx or times out (T4.7). The consumer rolls back the handler's transaction (and
    the claim), keeps the entry pending and resets its delivery count; XAUTOCLAIM brings it
    back after `min_idle` (60 s). A deferred event never goes to the dead letter, so:

    - check the quota before anything that costs money: a deferred event comes back every
      minute, possibly for a whole day;
    - an event deferred for ever stays pending for ever; T2.11 decides what to do about that;
    - a slow database (a statement timeout, a deadlock) is a failure, counted towards the dead
      letter: a handler that would rather wait raises `Deferred` itself.
    """


# SQLSTATEs of a lost or refused connection: class 08 (connection exception), and the server
# shutting down or starting up (57P01-57P03).
_OUTAGE_SQLSTATE_CLASS = "08"
_OUTAGE_SQLSTATES = frozenset({"57P01", "57P02", "57P03"})


def is_outage(error: BaseException) -> bool:
    """Whether `error` means the database or Redis is unreachable, not that the work failed.

    An outage is handled like `Deferred`, so a few minutes of downtime do not use up every
    event's attempts (review 🟠1). Only a lost connection counts (review 🟠C): psycopg raises
    OperationalError for a statement timeout, a deadlock or a row too large too, and those
    would fail the same way every time, so they go towards the dead letter.
    """
    if isinstance(error, RedisConnectionError | RedisTimeoutError):
        return True
    if isinstance(error, DBAPIError):
        if error.connection_invalidated:
            return True
        if not isinstance(error, OperationalError | InterfaceError):
            return False
        # No SQLSTATE: the error came from the client side (could not connect, socket closed).
        sqlstate = getattr(error.orig, "sqlstate", None)
        return (
            sqlstate is None
            or sqlstate.startswith(_OUTAGE_SQLSTATE_CLASS)
            or sqlstate in _OUTAGE_SQLSTATES
        )
    return False


_log = logging.getLogger("ai_service.messaging")
_tracer = trace.get_tracer("ai_service.messaging")
_PROPAGATOR = TraceContextTextMapPropagator()
# Fixed: the stream is known, and an event type is only trusted after parsing (review 🟡6).
SPAN_NAME = "events.core process"
# Outcomes that mark the span as an error and log a warning (dead: an error).
_FAILED = frozenset({"retry", "unavailable", "dead"})


@dataclass(frozen=True)
class _Result:
    outcome: str  # processed | duplicate | deferred | unavailable | retry | dead
    reason: str | None = None  # dead letter reason
    error_type: str | None = None  # exception class name


def _log_result(result: _Result, event: Event | None, deliveries: int) -> None:
    extra: dict[str, Any] = {"outcome": result.outcome, "deliveries": deliveries}
    if event is not None:
        extra |= {"event_id": str(event.event_id), "event_type": event.event_type}
    if result.reason is not None:
        extra["reason"] = result.reason
    if result.error_type is not None:
        extra["error_type"] = result.error_type
    if result.outcome == "dead":
        level = logging.ERROR
    elif result.outcome in _FAILED:
        level = logging.WARNING
    else:
        level = logging.INFO
    _log.log(level, "event handled", extra=extra)


# Every event_type in the contract, to tell an unknown type from a malformed known one.
EVENT_TYPES = frozenset(
    get_args(model.model_fields["event_type"].annotation)[0]
    for model in get_args(get_args(Event)[0])
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


def _rejection_reason(envelope: str) -> str:
    """`unknown_type` for a well-formed event of a type outside the contract, else invalid."""
    try:
        data = json.loads(envelope)
    except ValueError:
        return INVALID_ENVELOPE
    if isinstance(data, dict):
        event_type = cast(dict[str, Any], data).get("event_type")
        if isinstance(event_type, str) and event_type not in EVENT_TYPES:
            return UNKNOWN_TYPE
    return INVALID_ENVELOPE


class Consumer:
    """Reads `stream` as `name` in consumer group `group` and runs one handler per event type."""

    def __init__(
        self,
        *,
        redis: Redis,
        session_factory: Callable[[], Session],
        handlers: Mapping[str, Handler],
        stream: str = STREAM,
        group: str = GROUP,
        dead_stream: str = DEAD_STREAM,
        name: str | None = None,
        max_attempts: int = MAX_ATTEMPTS,
        min_idle_ms: int = MIN_IDLE_MS,
        backoff_base_ms: int = BACKOFF_BASE_MS,
        batch: int = BATCH,
        block_ms: int | None = BLOCK_MS,
    ) -> None:
        self.redis = redis
        self.session_factory = session_factory
        self.handlers = handlers
        self.stream = stream
        self.group = group
        self.dead_stream = dead_stream
        # A consumer that is gone leaves its entries pending; XAUTOCLAIM takes them over, so
        # the host name is enough (never XGROUP DELCONSUMER: it drops those entries).
        self.name = name or socket.gethostname()
        self.max_attempts = max_attempts
        self.min_idle_ms = min_idle_ms
        self.backoff_base_ms = backoff_base_ms
        self.batch = batch
        self.block_ms = block_ms
        self._cursor = "0-0"

    def ensure_group(self) -> None:
        """Create the group at the start of the stream (events sent before it existed count)."""
        try:
            self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def run_once(self) -> list[str]:
        """Handle the entries due again, then new ones; return each one's outcome."""
        outcomes = [self.handle(entry_id, fields, d) for entry_id, fields, d in self._reclaim()]
        block = None if outcomes else self.block_ms
        read = cast(
            list[tuple[str, list[tuple[str, dict[str, str]]]]],
            self.redis.xreadgroup(
                self.group, self.name, {self.stream: ">"}, count=self.batch, block=block
            ),
        )
        for _stream, entries in read or []:
            for entry_id, fields in entries:
                outcomes.append(self.handle(entry_id, fields, 1))
        return outcomes

    def handle(self, entry_id: str, fields: Mapping[str, str], deliveries: int) -> str:
        """Handle one entry delivered `deliveries` times; return its outcome.

        One span per entry, continuing the trace the envelope carries, and one log line. Both
        hold ids, counts, the outcome and class names only (ADR-0013); `event_id` and
        `event_type` only once the envelope has passed the contract (review 🟡6).
        """
        envelope = fields.get("envelope")
        event: Event | None = None
        rejected: str | None = INVALID_ENVELOPE if envelope is None else None
        if envelope is not None:
            try:
                event = parse_event(envelope)
            except ValidationError:
                rejected = _rejection_reason(envelope)
        carrier = event.trace_context.model_dump(exclude_none=True) if event else {}
        parent = _PROPAGATOR.extract(carrier)
        # Reset after the entry (review 🟡5): the loop is one context, and the next entry's
        # lines must not carry this user.
        user_token = user_id_var.set(str(event.user_id) if event else None)
        try:
            with _tracer.start_as_current_span(
                SPAN_NAME,
                context=parent,
                kind=SpanKind.CONSUMER,
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                span.set_attribute("deliveries", deliveries)
                if event is not None:
                    span.set_attribute("event_id", str(event.event_id))
                    span.set_attribute("event_type", event.event_type)
                result = self._process(entry_id, envelope or "", event, rejected, deliveries)
                span.set_attribute("outcome", result.outcome)
                if result.outcome in _FAILED:
                    # No description: an exception's message may hold data (ADR-0013).
                    span.set_status(StatusCode.ERROR)
                _log_result(result, event, deliveries)
                return result.outcome
        finally:
            user_id_var.reset(user_token)

    def _process(
        self,
        entry_id: str,
        envelope: str,
        event: Event | None,
        rejected: str | None,
        deliveries: int,
    ) -> "_Result":
        if event is None:
            return self._dead(entry_id, envelope, rejected or INVALID_ENVELOPE, deliveries)
        if not keys_belong_to_user(event):
            return self._dead(entry_id, envelope, USER_MISMATCH, deliveries)
        handler = self.handlers.get(event.event_type)
        if handler is None:
            return self._dead(entry_id, envelope, NO_HANDLER, deliveries)
        if deliveries > self.max_attempts:
            # Delivered again and again without a recorded failure: it crashes the consumer,
            # or it was handled and only its acknowledgement kept failing (review 🟡4).
            try:
                with self.session_factory() as session:
                    done = was_processed(session, self.group, event.event_id)
            except Exception as error:
                if not is_outage(error):
                    raise
                self._put_back(entry_id, deliveries)
                return _Result("unavailable", error_type=type(error).__name__)
            if done:
                self.redis.xack(self.stream, self.group, entry_id)
                return _Result("duplicate")
            return self._dead(entry_id, envelope, MAX_DELIVERIES, deliveries)
        try:
            with self.session_factory() as session, session.begin():
                if not claim(session, self.group, event.event_id):
                    outcome = "duplicate"
                else:
                    handler(session, event)
                    outcome = "processed"
        except Deferred:
            self._put_back(entry_id, deliveries)
            return _Result("deferred")
        except Exception as error:
            if is_outage(error):
                self._put_back(entry_id, deliveries)
                return _Result("unavailable", error_type=type(error).__name__)
            if deliveries >= self.max_attempts:
                return self._dead(entry_id, envelope, type(error).__name__, deliveries)
            self._back_off(entry_id, deliveries)
            return _Result("retry", error_type=type(error).__name__)
        self.redis.xack(self.stream, self.group, entry_id)
        return _Result(outcome)

    def _dead(self, entry_id: str, envelope: str, reason: str, deliveries: int) -> "_Result":
        send_to_dead(
            self.redis,
            dead_stream=self.dead_stream,
            stream=self.stream,
            group=self.group,
            entry_id=entry_id,
            envelope=envelope,
            reason=reason,
            deliveries=deliveries,
        )
        return _Result("dead", reason=reason)

    def _back_off(self, entry_id: str, failures: int) -> None:
        """Make the entry look idle for `min_idle - backoff`: XAUTOCLAIM takes it after backoff.

        JUSTID leaves the delivery count alone. IDLE is clamped at 0, which Redis would also do
        with a negative one; the clamp only makes that explicit.
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

    def _put_back(self, entry_id: str, deliveries: int) -> None:
        """Keep the entry pending as if this delivery had not happened.

        RETRYCOUNT sets the delivery count back to what it was before this delivery; the idle
        time restarts at 0, so XAUTOCLAIM takes the entry again after `min_idle`. JUSTID only
        returns the id; it does not override RETRYCOUNT (tests/messaging/test_deferred.py).
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

    def _reclaim(self) -> list[tuple[str, Mapping[str, str], int]]:
        """Entries idle for `min_idle_ms`, with how many times each has now been delivered."""
        reply = self.redis.xautoclaim(
            self.stream,
            self.group,
            self.name,
            self.min_idle_ms,
            start_id=self._cursor,
            count=self.batch,
        )
        # Redis ≥ 7 also returns the ids of entries trimmed while pending, and has already
        # dropped them from the pending list: nothing to do with them.
        self._cursor = str(reply[0])
        entries = cast(list[tuple[str, dict[str, str] | None]], reply[1])
        due: list[tuple[str, Mapping[str, str], int]] = []
        for entry_id, fields in entries:
            if fields is None:
                continue
            due.append((entry_id, fields, self._deliveries(entry_id)))
        return due

    def _deliveries(self, entry_id: str) -> int:
        rows = cast(
            list[dict[str, Any]],
            self.redis.xpending_range(self.stream, self.group, min=entry_id, max=entry_id, count=1),
        )
        return int(rows[0]["times_delivered"]) if rows else 1


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
            outcomes = consumer.run_once()
        except Exception:  # logged as class and stack, without the message (ADR-0013)
            _log.exception("event consumer round failed")
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
    from ai_service.clients.redis import redis_from_url
    from ai_service.config import get_settings
    from ai_service.db.session import get_session_factory
    from ai_service.handlers import HANDLERS
    from ai_service.logging import configure_logging
    from ai_service.telemetry import configure_tracing

    settings = get_settings()
    if settings.redis_url is None:
        sys.exit("AI_REDIS_URL is not set: the event consumer needs Redis")
    configure_logging(SERVICE, settings.log_level)
    provider = configure_tracing(SERVICE)
    consumer = Consumer(
        redis=redis_from_url(settings.redis_url.get_secret_value()),
        session_factory=get_session_factory(),
        handlers=HANDLERS,
    )
    stop = threading.Event()
    install_signal_handlers(stop)
    _log.info("consumer starting")
    try:
        run(consumer, stop)
    finally:
        provider.shutdown()
        _log.info("consumer stopped")


if __name__ == "__main__":
    main()
