"""Erase everything of one user (T6.3, ADR-0024, ADR-0001, ADR-0012). An operator's command.

Two logins, because no single one may do it all: a member of `core_eraser` can delete a user row
(its cascade is the only path the history triggers allow) but cannot write anything else, and
`core_app` can write the outbox and the jobs but is refused the history. So:

1. Eraser login: `DELETE FROM "user"`. The cascade removes the 35 tables that hold a `user_id`.
2. App login, one transaction: the outbox rows of the user go (`outbox.user_id` has no foreign
   key, so the cascade misses them), except `user.deleted.v1`; a fresh `user.deleted.v1` and the
   `erase_user_sweep` job are added. The event outlives the user row on purpose.
3. Objects under `users/{id}/` and every Redis entry that mentions the user.

Work still in flight when step 1 committed can write afterwards (a task in ai-service, a presigned
upload, a request that had already read the user). The sweep job runs the same cleanup again
`SWEEP_DELAY` later, and sends the event again so ai-service deletes what it wrote in between.
Every step can run again: running the command twice, or for a user that is gone, is safe.

Safety: nothing outside the database is touched unless the user row is really gone, so an eraser
URL that points at the wrong database fails closed instead of erasing a living user's files
(plan review O3). While the row exists the operator must give its email (Y1).
"""

import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from redis import Redis
from sqlalchemy import CursorResult, Engine, delete, text
from sqlalchemy.orm import Session

from core_api.clients.storage import ObjectStorage
from core_api.db.models import Outbox
from core_api.jobs.queue import enqueue_job
from core_api.messaging.dead_letter import DEAD_STREAM, purge_user
from core_api.messaging.envelope import UserDeleted
from core_api.messaging.outbox import enqueue_event

ERASE_USER_SWEEP = "erase_user_sweep"
KEPT_EVENT = "user.deleted.v1"
# Presigned uploads last at most 15 minutes (s3_presign_seconds <= 900) and an ai-service task
# is cut off well before that; 20 minutes covers both.
SWEEP_DELAY = {"minutes": 20}
# The streams events travel on; an envelope there can carry study content (notes, object keys).
STREAMS = ("events.core", "events.ai")
_SCAN_BATCH = 500

_log = logging.getLogger("core_api.domain")


class EraseRefused(Exception):
    """The command stopped before changing anything outside what it names. The message is safe
    to print (no user data, no connection string)."""


@dataclass(frozen=True)
class EraseResult:
    user_existed: bool
    outbox_rows: int
    objects: int
    dead_entries: int
    stream_entries: int


def erase_user(
    *,
    eraser_engine: Engine,
    app_engine: Engine,
    storage: ObjectStorage,
    redis: Redis,
    user_id: uuid.UUID,
    now: datetime,
    confirm_email: str | None = None,
    dead_stream: str = DEAD_STREAM,
    streams: Sequence[str] = STREAMS,
) -> EraseResult:
    existed = _delete_user_row(eraser_engine, app_engine, user_id, confirm_email)
    with Session(app_engine) as session:
        _require_gone(session, user_id)
        outbox_rows = purge_outbox(session, user_id)
        enqueue_event(session, UserDeleted(), user_id=user_id, now=now)
        enqueue_job(session, ERASE_USER_SWEEP, {"user_id": str(user_id)}, schedule_in=SWEEP_DELAY)
        session.commit()
    objects, dead, scrubbed = purge_outside_database(storage, redis, user_id, dead_stream, streams)
    _log.info(
        "user erased",
        extra={"deleted_count": outbox_rows + objects + dead + scrubbed},
    )
    return EraseResult(existed, outbox_rows, objects, dead, scrubbed)


def sweep_user(
    *,
    app_engine: Engine,
    storage: ObjectStorage,
    redis: Redis,
    user_id: uuid.UUID,
    now: datetime,
    dead_stream: str = DEAD_STREAM,
    streams: Sequence[str] = STREAMS,
) -> EraseResult:
    """The later pass: what was written after the erase, and the event once more for ai-service.
    Does nothing if the user is back (never erase a living user from a stale job)."""
    with Session(app_engine) as session:
        _require_gone(session, user_id)
        outbox_rows = purge_outbox(session, user_id)
        enqueue_event(session, UserDeleted(), user_id=user_id, now=now)
        session.commit()
    objects, dead, scrubbed = purge_outside_database(storage, redis, user_id, dead_stream, streams)
    return EraseResult(False, outbox_rows, objects, dead, scrubbed)


def purge_outbox(session: Session, user_id: uuid.UUID) -> int:
    """Delete the user's outbox rows except `user.deleted.v1`, sent or not: an event of someone
    who no longer exists must not reach ai-service. The one place that filters outbox by user."""
    result = session.execute(
        delete(Outbox)
        .where(Outbox.user_id == user_id, Outbox.event_type != KEPT_EVENT)
        .execution_options(synchronize_session=False)
    )
    return cast(CursorResult[Any], result).rowcount


def purge_outside_database(
    storage: ObjectStorage,
    redis: Redis,
    user_id: uuid.UUID,
    dead_stream: str = DEAD_STREAM,
    streams: Sequence[str] = STREAMS,
) -> tuple[int, int, int]:
    """Objects, dead letters and stream entries of the user; returns their counts."""
    # `user_id` is a UUID: no `..`, no `/`, no other user's prefix (ADR-0013).
    objects = storage.delete_prefix(f"users/{uuid.UUID(str(user_id))}/")
    dead = purge_user(redis, dead_stream=dead_stream, user_id=user_id)
    scrubbed = sum(scrub_stream(redis, stream, user_id) for stream in streams)
    return objects, dead, scrubbed


def scrub_stream(redis: Redis, stream: str, user_id: uuid.UUID) -> int:
    """XDEL the entries of `stream` that mention the user, except `user.deleted.v1` (an order
    not yet delivered). Reads in batches: the stream can hold 100,000 entries."""
    needle = str(user_id).encode()
    removed = 0
    cursor = "-"
    while True:
        entries = cast(
            list[tuple[bytes, dict[bytes, bytes]]],
            redis.xrange(stream, min=cursor, count=_SCAN_BATCH),
        )
        if not entries:
            return removed
        doomed = [
            entry_id
            for entry_id, fields in entries
            if needle in fields.get(b"envelope", b"").lower()
            and _event_type(fields.get(b"envelope", b"")) != KEPT_EVENT
        ]
        if doomed:
            redis.xdel(stream, *doomed)
            removed += len(doomed)
        if len(entries) < _SCAN_BATCH:
            return removed
        cursor = f"({entries[-1][0].decode()}"


def _event_type(envelope: bytes) -> str | None:
    try:
        parsed: Any = json.loads(envelope)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    event_type = cast(dict[str, Any], parsed).get("event_type")
    return event_type if isinstance(event_type, str) else None


def _delete_user_row(
    eraser_engine: Engine, app_engine: Engine, user_id: uuid.UUID, confirm_email: str | None
) -> bool:
    """Step 1; True if the row was there. Refuses a login that is not a `core_eraser` member
    (fail closed, not "the database said no"), a different database than the app's, and a
    living user without the matching email."""
    with eraser_engine.begin() as connection:
        member, eraser_db = connection.execute(
            text("SELECT pg_has_role(session_user, 'core_eraser', 'MEMBER'), current_database()")
        ).one()
        if not member:
            raise EraseRefused("the connection is not a member of core_eraser")
        with app_engine.connect() as app_connection:
            if app_connection.scalar(text("SELECT current_database()")) != eraser_db:
                raise EraseRefused("the eraser and the app connect to different databases")
        email = connection.scalar(text('SELECT email FROM "user" WHERE id = :id'), {"id": user_id})
        if email is None:
            return False
        if confirm_email is None or confirm_email.strip().lower() != str(email).lower():
            raise EraseRefused("the user exists: give --confirm-email with their exact email")
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": user_id})
        return True


def _require_gone(session: Session, user_id: uuid.UUID) -> None:
    if session.scalar(text('SELECT 1 FROM "user" WHERE id = :id'), {"id": user_id}) is not None:
        raise EraseRefused("the user still exists in the app's database; nothing else was touched")
