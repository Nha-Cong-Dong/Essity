import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned

QUESTION_STATUSES = frozenset({"active", "retired"})


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
        CheckConstraint("status IN ('active', 'retired')", name="status_known"),
        CheckConstraint("length(content_hash) = 64", name="content_hash_length"),
        UniqueConstraint("user_id", "subject_id", "content_hash"),
        UniqueConstraint("id", "user_id"),
        UniqueConstraint("id", "subject_id", "user_id"),
        Index(None, "subject_id", "status"),
    )

    subject_id: Mapped[uuid.UUID]
    level: Mapped[int] = mapped_column(SmallInteger)
    prompt: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str] = mapped_column(Text)
    rubric: Mapped[Any | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(10), default="active")
    content_hash: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[uuid.UUID]  # pipeline run in the ai database: no foreign key (ADR-0008)


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
