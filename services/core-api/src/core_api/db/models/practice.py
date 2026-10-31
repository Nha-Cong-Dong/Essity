import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Identity,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, one_of
from core_api.db.models.review import PHASES

# Practice has Easy (ADR-0029); the unit schedule's ratings stop at Good.
PRACTICE_RATINGS = (1, 2, 3, 4)


class PracticeState(UserOwned, Base):
    """FSRS state of one practice question (T8.3), mirroring `MemoryState` per question and kept
    apart from it: practice never writes the unit schedule. `removed_at` leaves the row, so the
    schedule survives a question taken out of practice and put back."""

    __tablename__ = "practice_state"
    __table_args__ = (
        ForeignKeyConstraint(
            ["question_id", "user_id"], ["question.id", "question.user_id"], ondelete="NO ACTION"
        ),
        CheckConstraint(one_of("phase", PHASES), name="phase_known"),
        CheckConstraint("(phase = 'relearning') = (step IS NOT NULL)", name="step_when_relearning"),
        # user_id in the key, as in memory_state: an upsert of another user's question inserts
        # and the composite key refuses.
        UniqueConstraint("user_id", "question_id"),
        Index(
            "ix_practice_state_user_id_due",
            "user_id",
            "due",
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    question_id: Mapped[uuid.UUID]
    phase: Mapped[str] = mapped_column(String(10))
    step: Mapped[int | None] = mapped_column(SmallInteger)
    stability: Mapped[float] = mapped_column(Float(precision=53))
    difficulty: Mapped[float] = mapped_column(Float(precision=53))
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_review: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PracticeLog(UserOwned, Base):
    """One FSRS review of a practice question (T8.3), added and never changed, like
    `review_log` (same trigger function, so T2.22 opens one way for both). `grade_id` is the
    grade of the attempt that earned it: one log row per grade."""

    __tablename__ = "practice_log"
    __table_args__ = (
        ForeignKeyConstraint(
            ["question_id", "user_id"], ["question.id", "question.user_id"], ondelete="NO ACTION"
        ),
        ForeignKeyConstraint(
            ["grade_id", "user_id"], ["grade.id", "grade.user_id"], ondelete="NO ACTION"
        ),
        CheckConstraint(
            f"rating IN ({', '.join(map(str, PRACTICE_RATINGS))})", name="rating_known"
        ),
        UniqueConstraint("grade_id"),
        Index(None, "user_id", "reviewed_at", "seq"),
        Index(None, "question_id"),
    )

    question_id: Mapped[uuid.UUID]
    rating: Mapped[int] = mapped_column(SmallInteger)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grade_id: Mapped[uuid.UUID]
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
