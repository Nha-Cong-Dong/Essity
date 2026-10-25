"""Skip an event already handled (T4.3, ADR-0006): delivery is at least once.

`claim` runs inside the transaction that also holds the handler's writes. `INSERT … ON CONFLICT
DO NOTHING` waits for a concurrent transaction holding the same key and then reports the
conflict, so two consumers given the same event never both run its handler, and a rolled-back
handler leaves no row behind.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ai_service.db.models import ProcessedEvent


def claim(session: Session, consumer: str, event_id: uuid.UUID) -> bool:
    """Record `event_id` for `consumer`; False when it was already recorded (a duplicate)."""
    inserted = session.execute(
        insert(ProcessedEvent)
        .values(consumer=consumer, event_id=event_id)
        .on_conflict_do_nothing()
        .returning(ProcessedEvent.event_id)
    ).first()
    return inserted is not None


def was_processed(session: Session, consumer: str, event_id: uuid.UUID) -> bool:
    """Whether `event_id` was handled and committed (read only)."""
    found = session.scalar(
        select(ProcessedEvent.event_id).where(
            ProcessedEvent.consumer == consumer, ProcessedEvent.event_id == event_id
        )
    )
    return found is not None
