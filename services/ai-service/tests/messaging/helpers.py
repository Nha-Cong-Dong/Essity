"""Events and a recording handler for the consumer's tests."""

import json
import uuid
from collections.abc import Callable
from typing import Any

from redis import Redis
from sqlalchemy.orm import Session

from ai_service.messaging.envelope import Event

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_SPAN_ID = "00f067aa0ba902b7"
DOCUMENT_UPLOADED = "document.uploaded.v1"


def uploaded(
    user_id: uuid.UUID | None = None,
    *,
    key_owner: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    traceparent: str | None = f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01",
) -> dict[str, Any]:
    """A valid `document.uploaded.v1`; `key_owner` puts another user's id in its object key."""
    user = user_id or uuid.uuid4()
    subject = uuid.uuid4()
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": DOCUMENT_UPLOADED,
        "schema_version": 1,
        "occurred_at": "2026-10-26T08:30:00.000000Z",
        "user_id": str(user),
        "trace_context": {"traceparent": traceparent} if traceparent else {},
        "payload": {
            "document_id": str(uuid.uuid4()),
            "subject_id": str(subject),
            "object_key": f"users/{key_owner or user}/subjects/{subject}/raw/{'a' * 64}.pdf",
        },
    }


def publish(redis: Redis, stream: str, event: dict[str, Any] | str) -> str:
    """XADD one entry as the relay writes it: one field, `envelope`, holding the JSON text."""
    envelope = event if isinstance(event, str) else json.dumps(event)
    return str(redis.xadd(stream, {"envelope": envelope}))


class Recorder:
    """A handler that records the events it was given, and can fail on demand."""

    def __init__(self, fail_with: Callable[[], Exception] | None = None) -> None:
        self.calls: list[Event] = []
        self.fail_with = fail_with

    def __call__(self, session: Session, event: Event) -> None:
        self.calls.append(event)
        if self.fail_with is not None:
            raise self.fail_with()


class Boom(Exception):
    """A handler bug. Its message must never reach a log, a span or the dead letter."""


SECRET_DETAIL = "answer: TCP dùng bắt tay ba bước"


def boom() -> Exception:
    return Boom(SECRET_DETAIL)
