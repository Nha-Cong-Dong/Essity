"""`enqueue_event`: send an event to ai-service through the transactional outbox (T4.2, ADR-0006).

The event is a row in `outbox`, added to the caller's session: it is committed with the data it
announces, or rolled back with it. `core-relay` (`messaging.relay`) later writes it to the
`events.core` stream. Delivery is at least once and **order is not guaranteed**: a row whose send
failed waits its backoff while later rows go ahead, and a consumer may see an event twice.
"""

import uuid
from datetime import datetime
from typing import Any, get_args

from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy.orm import Session

from core_api.db.models import Outbox
from core_api.messaging.envelope import (
    DocumentUploaded,
    DocumentUploadedEvent,
    Event,
    GradeRequested,
    GradeRequestedEvent,
    SessionConfirmed,
    SessionConfirmedEvent,
    SubmissionCreated,
    SubmissionCreatedEvent,
    TraceContext,
    UserDeleted,
    UserDeletedEvent,
)

CorePayload = DocumentUploaded | SessionConfirmed | SubmissionCreated | GradeRequested | UserDeleted
CoreEvent = (
    DocumentUploadedEvent
    | SessionConfirmedEvent
    | SubmissionCreatedEvent
    | GradeRequestedEvent
    | UserDeletedEvent
)

# The events core-api sends (core → ai), by payload. The rest arrive on `events.ai`.
_EVENTS: dict[type[CorePayload], type[CoreEvent]] = {
    DocumentUploaded: DocumentUploadedEvent,
    SessionConfirmed: SessionConfirmedEvent,
    SubmissionCreated: SubmissionCreatedEvent,
    GradeRequested: GradeRequestedEvent,
    UserDeleted: UserDeletedEvent,
}

_PROPAGATOR = TraceContextTextMapPropagator()


def _event_types() -> dict[Any, str]:
    """Every event type of the contract, by its payload class."""
    events: tuple[Any, ...] = get_args(get_args(Event)[0])
    return {
        event.model_fields["payload"].annotation: get_args(
            event.model_fields["event_type"].annotation
        )[0]
        for event in events
    }


_EVENT_TYPES = _event_types()


def current_trace_context() -> TraceContext:
    """W3C trace context of the current span; empty outside any span."""
    carrier: dict[str, str] = {}
    _PROPAGATOR.inject(carrier)
    return TraceContext.model_validate(carrier)


def enqueue_event(
    session: Session, payload: CorePayload, *, user_id: uuid.UUID, now: datetime
) -> uuid.UUID:
    """Add the event carrying `payload` for `user_id` to `session`; return its event_id.

    Nothing is committed here: the caller's commit sends it, the caller's rollback drops it.
    `now` (UTC) is when it happened and when it may first be sent. The event is validated
    against the contract first (`ValidationError`), and only core → ai events are accepted
    (`ValueError` otherwise).
    """
    event_class = _EVENTS.get(type(payload))
    if event_class is None:
        raise ValueError(f"core-api does not send {_EVENT_TYPES.get(type(payload))}")
    event = event_class.model_validate(
        {
            "event_id": uuid.uuid4(),
            "event_type": _EVENT_TYPES[event_class.model_fields["payload"].annotation],
            "schema_version": 1,
            "occurred_at": now,
            "user_id": user_id,
            "trace_context": current_trace_context(),
            "payload": payload,
        }
    )
    wire = event.model_dump(mode="json")
    session.add(
        Outbox(
            id=event.event_id,
            user_id=event.user_id,
            event_type=event.event_type,
            payload=wire["payload"],
            trace_context={k: v for k, v in wire["trace_context"].items() if v is not None},
            occurred_at=event.occurred_at,
            available_at=event.occurred_at,
        )
    )
    return event.event_id
