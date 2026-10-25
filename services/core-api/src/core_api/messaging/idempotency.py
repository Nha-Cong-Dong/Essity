"""`claim`: handle each event once (T4.4, ADR-0006).

Events arrive at least once. A consumer claims an event in the same transaction as its handler:
if the handler's work commits, so does the claim, and a second delivery finds it and skips the
handler; if the work rolls back, so does the claim, and the next delivery runs it again.
"""

import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core_api.db.models import ProcessedEvent


def claim(session: Session, *, consumer: str, event_id: uuid.UUID, now: datetime) -> bool:
    """True when `consumer` had not yet handled `event_id`: run the handler. False: skip it.

    Nothing is committed here. Two transactions claiming the same event at once: the second
    waits on the first's row, then gets False if it committed, True if it rolled back.
    """
    claimed = session.execute(
        insert(ProcessedEvent)
        .values(consumer=consumer, event_id=event_id, processed_at=now)
        .on_conflict_do_nothing(index_elements=["consumer", "event_id"])
        .returning(ProcessedEvent.event_id)
    ).scalar_one_or_none()
    return claimed is not None
