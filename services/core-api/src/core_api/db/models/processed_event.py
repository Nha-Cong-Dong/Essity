"""Events a consumer has handled (T4.4, ADR-0006): delivery is at least once, so a consumer
records each `event_id` in the transaction of its handler and skips one it has seen.

Layer ⑤ (ARCHITECTURE §6.2). Written through `messaging.idempotency.claim` only, never through a
repository. No `user_id`: a row holds an event id and a time, nothing about the user.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base


class ProcessedEvent(Base):
    __tablename__ = "processed_event"

    # Which consumer handled it: two consumers of one event each handle it once.
    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
