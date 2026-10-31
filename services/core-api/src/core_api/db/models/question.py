import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, not_blank, one_of

QUESTION_STATUSES = frozenset({"active", "retired"})
# v2 (T7.1): where a question comes from, how far it passed the quality filter, who wrote the
# answer.
QUESTION_SOURCES = frozenset({"bank", "generated", "review_auto"})
QUALITY_STATUSES = frozenset({"pending", "ok", "rejected"})
ANSWER_ORIGINS = frozenset({"bank", "ai", "user"})
# Where a question type's reference time comes from (spec v2 §16.1 Q-C).
REF_ORIGINS = frozenset({"default", "rubric", "learner_median", "user"})


class Question(UserOwned, Base):
    """A question of one level (us-04b), on one or more units of its subject (question_unit).

    `content_hash` (domain.question_hash) is unique per user and subject (plan D12): a seed run
    twice adds nothing, and the same question asked in two subjects is two questions.
    """

    __tablename__ = "question"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subject_id", "user_id"], ["subject.id", "subject.user_id"], ondelete="CASCADE"
        ),
        CheckConstraint("level BETWEEN 1 AND 3", name="level_range"),
        CheckConstraint(not_blank("prompt"), name="prompt_not_blank"),
        CheckConstraint(not_blank("reference_answer"), name="answer_not_blank"),
        CheckConstraint("status IN ('active', 'retired')", name="status_known"),
        CheckConstraint(one_of("source", QUESTION_SOURCES), name="source_known"),
        CheckConstraint(one_of("quality_status", QUALITY_STATUSES), name="quality_status_known"),
        CheckConstraint(one_of("answer_origin", ANSWER_ORIGINS), name="answer_origin_known"),
        CheckConstraint(
            "(answer_text IS NULL) = (answer_origin IS NULL)", name="answer_text_with_origin"
        ),
        CheckConstraint("unit_rev IS NULL OR unit_rev >= 0", name="unit_rev_not_negative"),
        # A bank or generated question has no pipeline run behind it.
        CheckConstraint(
            "source <> 'review_auto' OR run_id IS NOT NULL", name="review_auto_has_run"
        ),
        # NO ACTION, not CASCADE: dropping a type never drops its questions.
        ForeignKeyConstraint(
            ["type_id", "subject_id", "user_id"],
            ["question_type.id", "question_type.subject_id", "question_type.user_id"],
        ),
        CheckConstraint("length(content_hash) = 64", name="content_hash_length"),
        # Unique among the active ones: a question whose answer changed is retired and replaced
        # (T2.2), so retired ones may repeat the hash.
        Index(
            "uq_question_active_content_hash",
            "user_id",
            "subject_id",
            "content_hash",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        # The question-bank file a question was read from (T8.1). NO ACTION: deleting the file
        # never takes questions that already have a schedule.
        ForeignKeyConstraint(
            ["bank_document_id", "subject_id", "user_id"],
            ["document.id", "document.subject_id", "document.user_id"],
            ondelete="NO ACTION",
        ),
        CheckConstraint(
            "bank_ord IS NULL OR bank_document_id IS NOT NULL", name="bank_ord_needs_document"
        ),
        CheckConstraint("bank_ord IS NULL OR bank_ord >= 0", name="bank_ord_not_negative"),
        UniqueConstraint("id", "user_id"),
        UniqueConstraint("id", "subject_id", "user_id"),
        Index(None, "subject_id", "status"),
        Index(None, "bank_document_id", "bank_ord"),
    )

    subject_id: Mapped[uuid.UUID]
    level: Mapped[int] = mapped_column(SmallInteger)
    prompt: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str] = mapped_column(Text)
    rubric: Mapped[Any | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), default="active")
    content_hash: Mapped[str] = mapped_column(String(64))
    # Pipeline run in the ai database: no foreign key (ADR-0008). None for bank and generated ones.
    run_id: Mapped[uuid.UUID | None]
    # Old questions came from the review pipeline: that is what they stay.
    source: Mapped[str] = mapped_column(String(12), server_default="review_auto")
    type_id: Mapped[uuid.UUID | None]
    quality_status: Mapped[str] = mapped_column(String(10), server_default="ok")
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_origin: Mapped[str | None] = mapped_column(String(4))
    kept_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The unit revision the question was written from (made again, lazily, when that moves on).
    unit_rev: Mapped[int | None] = mapped_column(Integer)
    # Where it sits in its question-bank file (T8.1); NULL for a question not read from one.
    bank_document_id: Mapped[uuid.UUID | None]
    bank_ord: Mapped[int | None] = mapped_column(Integer)


class QuestionUnit(UserOwned, Base):
    """Which units a question checks. `subject_id` is carried so the database itself refuses a
    question and a unit of different subjects (plan D9), as `user_id` does for owners."""

    __tablename__ = "question_unit"
    __table_args__ = (
        ForeignKeyConstraint(
            ["question_id", "subject_id", "user_id"],
            ["question.id", "question.subject_id", "question.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["unit_id", "subject_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.subject_id", "knowledge_unit.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("question_id", "unit_id"),
    )

    subject_id: Mapped[uuid.UUID]
    question_id: Mapped[uuid.UUID]
    unit_id: Mapped[uuid.UUID] = mapped_column(index=True)


class QuestionType(UserOwned, Base):
    """A kind of question of one subject (T7.1, spec v2 §16.1 Q-C): mastery and the reference time
    are counted per type."""

    __tablename__ = "question_type"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subject_id", "user_id"], ["subject.id", "subject.user_id"], ondelete="CASCADE"
        ),
        UniqueConstraint("id", "user_id"),
        # Target of question.type_id: a question never has the type of another subject.
        UniqueConstraint("id", "subject_id", "user_id"),
        UniqueConstraint("subject_id", "name"),
        CheckConstraint(not_blank("name"), name="name_not_blank"),
        CheckConstraint("ref_time_s > 0", name="ref_time_positive"),
        CheckConstraint(one_of("ref_origin", REF_ORIGINS), name="ref_origin_known"),
    )

    subject_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(100))
    ref_time_s: Mapped[int] = mapped_column(Integer)
    ref_origin: Mapped[str] = mapped_column(String(14))


class QuestionSection(UserOwned, Base):
    """Which outline sections a question belongs to (its readiness is counted on them)."""

    __tablename__ = "question_section"
    __table_args__ = (
        ForeignKeyConstraint(
            ["question_id", "subject_id", "user_id"],
            ["question.id", "question.subject_id", "question.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["section_id", "subject_id", "user_id"],
            ["doc_section.id", "doc_section.subject_id", "doc_section.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("question_id", "section_id"),
        Index(None, "section_id"),
    )

    subject_id: Mapped[uuid.UUID]
    question_id: Mapped[uuid.UUID]
    section_id: Mapped[uuid.UUID]
