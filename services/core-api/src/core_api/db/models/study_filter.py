import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, one_of

FILTER_MODES = frozenset({"only", "defer"})


class StudyFilter(Base):
    """The suggestion filter a command set on one subject (T9.2b, ADR-0030): "only" or "defer"
    its cards until a day. One row per user and subject for good: undoing a command clears `mode`
    and raises `rev`, never deletes, so `rev` cannot return to a value an undo already saw (ABA).
    A row with no `mode` is no filter."""

    __tablename__ = "study_filter"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subject_id", "user_id"], ["subject.id", "subject.user_id"], ondelete="CASCADE"
        ),
        CheckConstraint(one_of("mode", FILTER_MODES), name="mode_known"),
        CheckConstraint("rev >= 1", name="rev_from_one"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    mode: Mapped[str | None] = mapped_column(String(5))
    until: Mapped[date | None] = mapped_column(Date)
    rev: Mapped[int] = mapped_column(Integer, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(UTC)
    )
