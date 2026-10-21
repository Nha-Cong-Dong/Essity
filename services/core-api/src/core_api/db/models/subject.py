import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned


class Subject(UserOwned, Base):
    """A subject space (US-01): created with a name and an exam date, nothing else."""

    __tablename__ = "subject"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        # Target of exam's composite foreign key: an exam's owner must be its subject's owner.
        UniqueConstraint("id", "user_id"),
    )

    name: Mapped[str] = mapped_column(String(200))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Exam(UserOwned, Base):
    """The exam of a subject. MVP: one per subject (Q17), held by a unique constraint; for
    mid-term exams (outside the MVP) a migration drops it.

    The page range covered by the exam (Q1, "ready" metric) is added with the document table.
    """

    __tablename__ = "exam"
    __table_args__ = (
        # (subject_id, user_id) -> subject(id, user_id): the database itself refuses an exam
        # attached to someone else's subject.
        ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subject.id", "subject.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("subject_id"),
    )

    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    exam_date: Mapped[date] = mapped_column(Date)
