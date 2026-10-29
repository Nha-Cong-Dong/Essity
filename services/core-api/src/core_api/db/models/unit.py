import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    REAL,
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
    # The section of the document it sits in (us-02b AC1). A plain UUID for now: there is no
    # `doc_section` table to point at yet (T4.17 writes NULL until there is).
    section_id: Mapped[uuid.UUID | None]
    # The pipeline run that made it, in the ai database: a plain UUID, no foreign key (ADR-0008).
    run_id: Mapped[uuid.UUID]


class Anchor(UserOwned, Base):
    """Where a unit comes from, down to the characters (ADR-0008, fine-grained from the start).

    `document_id` is the document the quote is read from: set only for a document anchor, and gone
    with that document (T4.17). A seeded anchor may have none (the seed has no document).
    """

    __tablename__ = "anchor"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            ondelete="CASCADE",
        ),
        # Never a document on another user's account: the pair points at document(id, user_id).
        ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["document.id", "document.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(one_of("source", ANCHOR_SOURCES), name="source_known"),
        CheckConstraint(
            "source = 'document' OR document_id IS NULL", name="notes_have_no_document"
        ),
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
    document_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    page_no: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[Any | None] = mapped_column(JSONB)
    quote_text: Mapped[str] = mapped_column(Text)
    run_id: Mapped[uuid.UUID]


class UnitLineage(UserOwned, Base):
    """Where a unit went when it was split or merged again (ADR-0008, us-02b §9 #3): the review
    history of `old_unit_id` moves to `new_unit_id` along these rows.

    `confidence` is null until a threshold is decided (us-02b §9 #8).
    """

    __tablename__ = "unit_lineage"
    __table_args__ = (
        ForeignKeyConstraint(
            ["old_unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["new_unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("old_unit_id <> new_unit_id", name="old_is_not_new"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_unit"
        ),
        UniqueConstraint("old_unit_id", "new_unit_id"),
        Index(None, "new_unit_id"),
    )

    old_unit_id: Mapped[uuid.UUID] = mapped_column(index=True)
    new_unit_id: Mapped[uuid.UUID]
    confidence: Mapped[float | None] = mapped_column(REAL)
    run_id: Mapped[uuid.UUID]
