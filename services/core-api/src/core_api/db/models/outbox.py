"""The transactional outbox (T4.2, ADR-0006): events core-api sends, written in the same
transaction as the data they announce, then relayed to Redis by `core-relay`.

Layer ⑤ (ARCHITECTURE §6.2). `user_id` is a plain column, not a foreign key to `user` (plan E2):
`user.deleted.v1` must outlive the user it announces. Rows are written through
`messaging.outbox.enqueue_event` and read by the relay only, never through a repository.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, one_of

# Events core-api sends (core → ai, ARCHITECTURE §7.3). The others arrive on `events.ai`.
OUTBOX_EVENT_TYPES = frozenset(
    {"document.uploaded.v1", "session.confirmed.v1", "grade.requested.v1", "user.deleted.v1"}
)


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint(one_of("event_type", OUTBOX_EVENT_TYPES), name="event_type"),
        CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        # What the relay reads: unsent rows that are due, oldest first.
        Index(
            "ix_outbox_unsent",
            "available_at",
            "seq",
            postgresql_where=text("sent_at IS NULL"),
        ),
    )

    # The event's event_id.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    user_id: Mapped[uuid.UUID]
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    trace_context: Mapped[dict[str, str]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Not before this time: pushed back after a failed send (relay backoff).
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Class name of the last send error only; its message may hold data.
    last_error: Mapped[str | None] = mapped_column(String(200))
