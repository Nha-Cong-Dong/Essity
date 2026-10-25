import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, not_blank, one_of

# PRD US-02b: the five kinds of knowledge unit (plan D4).
UNIT_KINDS = frozenset({"concept", "mechanism", "comparison", "formula", "example"})
UNIT_STATUSES = frozenset({"active", "split", "merged", "retired"})
# Where an anchor's quote comes from: a document page, or the user's own notes (us-02b AC5).
ANCHOR_SOURCES = frozenset({"document", "notes"})


class KnowledgeUnit(UserOwned, Base):
    """A knowledge unit (layer 2, ADR-0008): what a question checks and the schedule tracks.

    Never deleted once reviewed: review_log points at it (plan D10). A unit that is split, merged
    or dropped changes `status`; `unit_lineage` (T4.15) records where it went.
    """

    __tablename__ = "knowledge_unit"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subject_id", "user_id"], ["subject.id", "subject.user_id"], ondelete="CASCADE"
        ),
        CheckConstraint(not_blank("title"), name="title_not_blank"),
        CheckConstraint(one_of("kind", UNIT_KINDS), name="kind_known"),
        CheckConstraint(one_of("status", UNIT_STATUSES), name="status_known"),
        # Targets of the composite foreign keys below and in question_unit (plan D9).
        UniqueConstraint("id", "user_id"),
        UniqueConstraint("id", "subject_id", "user_id"),
        Index(None, "subject_id", "status"),
    )

    subject_id: Mapped[uuid.UUID]
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), default="active")
    # "Không cần ôn phần này" (T2.23): never asked while set; schedule and history stay as they are.
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The pipeline run that made it, in the ai database: a plain UUID, no foreign key (ADR-0008).
    run_id: Mapped[uuid.UUID]


class Anchor(UserOwned, Base):
    """Where a unit comes from, down to the characters (ADR-0008, fine-grained from the start).

    `document_id` (with a CHECK that a document anchor has its page) and `section_id` arrive
    with the first task that writes document anchors (T4.13/T4.15), not with `document` (T4.5).
    """

    __tablename__ = "anchor"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(one_of("source", ANCHOR_SOURCES), name="source_known"),
        CheckConstraint(not_blank("quote_text"), name="quote_not_blank"),
        CheckConstraint("page_no IS NULL OR page_no >= 1", name="page_from_one"),
        CheckConstraint(
            "(char_start IS NULL) = (char_end IS NULL)", name="char_range_both_or_neither"
        ),
        CheckConstraint("char_start IS NULL OR char_start >= 0", name="char_start_not_negative"),
        CheckConstraint("char_end IS NULL OR char_end >= char_start", name="char_end_after_start"),
        CheckConstraint("bbox IS NULL OR jsonb_typeof(bbox) = 'array'", name="bbox_is_array"),
    )

    unit_id: Mapped[uuid.UUID] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(String(10))
    page_no: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[Any | None] = mapped_column(JSONB)
    quote_text: Mapped[str] = mapped_column(Text)
    run_id: Mapped[uuid.UUID]
