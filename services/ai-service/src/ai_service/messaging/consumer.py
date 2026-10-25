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

Same pattern as core-api's consumer (T4.4) but not shared by import (ADR-0003, PLAN T4.4).
"""

import logging
import socket
from collections.abc import Callable, Mapping
from typing import Any, cast

from redis import Redis
from redis.exceptions import ResponseError
from sqlalchemy.orm import Session

from ai_service.messaging.envelope import Event, parse_event
from ai_service.messaging.idempotency import claim

STREAM = "events.core"
# Also the `consumer` column of `processed_event`.
GROUP = "ai-service"
DEAD_STREAM = "events.dead"
# Deliveries of one entry before it goes to the dead letter (plan E9).
MAX_ATTEMPTS = 5
# An entry read and not acknowledged for this long is taken back (plan E9). Must exceed the
# longest handler when several consumers run, or two of them handle the same entry at once
# (the claim then makes the second wait and skip).
MIN_IDLE_MS = 60_000
BATCH = 10
BLOCK_MS = 1_000

Handler = Callable[[Session, Event], None]
"""Handles one event inside the consumer's transaction.

- Writes to the database only through `session`; the consumer commits it with the claim.
- Any other effect (an object written, an event sent) must be idempotent on the event: keyed by
  `event_id` or a run id derived from it, because the event may be handled again after a
  failure.
- Takes the user from `event.user_id`, never from the payload: the consumer has checked that
  every object key in the payload belongs to that user (F2).
"""

_log = logging.getLogger("ai_service.messaging")


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
        """Handle one entry delivered `deliveries` times; return its outcome."""
        event = parse_event(fields["envelope"])
        handler = self.handlers[event.event_type]
        try:
            with self.session_factory() as session, session.begin():
                if not claim(session, self.group, event.event_id):
                    outcome = "duplicate"
                else:
                    handler(session, event)
                    outcome = "processed"
        except Exception:
            return "retry"
        self.redis.xack(self.stream, self.group, entry_id)
        return outcome

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
