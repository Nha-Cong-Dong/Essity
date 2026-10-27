"""Review history (layer 3, append-only) and the schedule cache (layer 4), ARCH §6.2, T2.3.

Layer 3 is the most valuable data in the system (PRD §6): triggers in migration 0008 refuse to
change or delete it, even when an account is deleted, until T2.22 opens one way for a database
role of its own, `core_eraser` (plan D1). `memory_state` is a cache rebuilt from `review_log`
(T2.6).
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, one_of
from core_api.domain.scheduling.fsrs_adapter import Phase
from core_api.domain.scheduling.rating import ReviewRating, Verdict

STOP_REASONS = frozenset({"completed", "user_stopped"})
ATTEMPT_STATUSES = frozenset({"draft", "submitted"})
# "fake": the fake grader in local and test (T2.13, R41); a fake grade is never real evidence.
GRADE_SOURCES = frozenset({"ai", "fake", "user_override", "system"})
OVERALL = frozenset(verdict.value for verdict in Verdict)
# A unit is judged correct, partial or incorrect; "forgot" is a whole answer, never a unit's.
UNIT_VERDICTS = OVERALL - {Verdict.FORGOT.value}
RATINGS = sorted(rating.value for rating in ReviewRating)
PHASES = frozenset(phase.value for phase in Phase)
# MVP: one facet per unit (ADR-0009). It is not the question's level (plan D4).
FACETS = frozenset({"core"})
MAX_ANSWER_CHARS = 20_000  # a wide safety net; T2.9 sets the real limit at the API


def _seq() -> Mapped[int]:
    # Order within an attempt or a unit: created_at is the same for every row of a transaction
    # (plan D2).
    return mapped_column(BigInteger, Identity(always=True))


class ReviewSession(UserOwned, Base):
    """One sitting (us-08). Closed once, with its reason; then it no longer changes."""

    __tablename__ = "review_session"
    __table_args__ = (
        CheckConstraint(
            f"stop_reason IS NULL OR {one_of('stop_reason', STOP_REASONS)}",
            name="stop_reason_known",
        ),
        CheckConstraint("(ended_at IS NULL) = (stop_reason IS NULL)", name="ended_with_reason"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ends_after_start"),
        UniqueConstraint("id", "user_id"),
        Index(None, "user_id", "learning_day"),
        # One open session per learning day (T2.9 plan C4): two tabs pressing "Bắt đầu" get the
        # same one. A session left open on an earlier day does not block a new day's.
        Index(
            "uq_review_session_open_per_day",
            "user_id",
            "learning_day",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    learning_day: Mapped[date] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str | None] = mapped_column(String(20))


class ReviewSessionItem(UserOwned, Base):
    """The questions of a session, in order, fixed when it starts (T2.9 plan C1): "7/14" keeps
    its total, and a backlog does not keep refilling the session. Append-only (plan C3)."""

    __tablename__ = "review_session_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_session_id", "user_id"],
            ["review_session.id", "review_session.user_id"],
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["question_id", "user_id"], ["question.id", "question.user_id"], ondelete="NO ACTION"
        ),
        CheckConstraint("position >= 1", name="position_from_one"),
        UniqueConstraint("review_session_id", "position"),
        UniqueConstraint("review_session_id", "question_id"),
    )

    review_session_id: Mapped[uuid.UUID]
    position: Mapped[int] = mapped_column(SmallInteger)
    question_id: Mapped[uuid.UUID] = mapped_column(index=True)


class Attempt(UserOwned, Base):
    """An answer to one question in one session. A draft may change; once submitted, never."""

    __tablename__ = "attempt"
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_session_id", "user_id"],
            ["review_session.id", "review_session.user_id"],
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["question_id", "user_id"], ["question.id", "question.user_id"], ondelete="NO ACTION"
        ),
        CheckConstraint(one_of("status", ATTEMPT_STATUSES), name="status_known"),
        CheckConstraint(
            "(status = 'submitted') = (submitted_at IS NOT NULL)", name="submitted_has_time"
        ),
        CheckConstraint(f"char_length(answer_text) <= {MAX_ANSWER_CHARS}", name="answer_length"),
        UniqueConstraint("review_session_id", "question_id"),
        UniqueConstraint("id", "user_id"),
    )

    review_session_id: Mapped[uuid.UUID]
    question_id: Mapped[uuid.UUID] = mapped_column(index=True)
    answer_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    dont_remember: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(10), default="draft", server_default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Grade(UserOwned, Base):
    """A judgement of an attempt. A new judgement (override, regrade) is a new row; the current
    one is the attempt's highest `seq`, never a flag that would need an UPDATE (ARCH §6.2)."""

    __tablename__ = "grade"
    __table_args__ = (
        ForeignKeyConstraint(
            ["attempt_id", "user_id"], ["attempt.id", "attempt.user_id"], ondelete="NO ACTION"
        ),
        CheckConstraint(one_of("source", GRADE_SOURCES), name="source_known"),
        CheckConstraint(one_of("overall", OVERALL), name="overall_known"),
        # "Không nhớ" is graded by the system, and only it (plan D6).
        CheckConstraint("(overall = 'forgot') = (source = 'system')", name="forgot_by_system"),
        CheckConstraint(
            "understanding IS NULL OR (overall NOT IN ('incorrect', 'forgot')"
            " AND understanding BETWEEN 1 AND 3)",
            name="understanding_when_right",
        ),
        UniqueConstraint("id", "user_id"),
        Index(None, "attempt_id", "seq"),
    )

    attempt_id: Mapped[uuid.UUID]
    source: Mapped[str] = mapped_column(String(20))
    overall: Mapped[str] = mapped_column(String(10))
    # The scale is T2.12's; hidden on screen when wrong or forgotten (us-05 §9 #9).
    understanding: Mapped[int | None] = mapped_column(SmallInteger)
    missing: Mapped[Any] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    anchors_used: Mapped[Any] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    run_id: Mapped[uuid.UUID | None]  # pipeline run in the ai database: no foreign key
    seq: Mapped[int] = _seq()


class GradeUnit(UserOwned, Base):
    """A grade's verdict on one unit: one row per unit (us-05 AC9)."""

    __tablename__ = "grade_unit"
    __table_args__ = (
        ForeignKeyConstraint(
            ["grade_id", "user_id"], ["grade.id", "grade.user_id"], ondelete="NO ACTION"
        ),
        ForeignKeyConstraint(
            ["unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            ondelete="NO ACTION",
        ),
        CheckConstraint(one_of("verdict", UNIT_VERDICTS), name="verdict_known"),
        UniqueConstraint("grade_id", "unit_id"),
        # Target of review_log's key: a log row points at a unit this grade judged (P2).
        UniqueConstraint("grade_id", "unit_id", "user_id"),
    )

    grade_id: Mapped[uuid.UUID]
    unit_id: Mapped[uuid.UUID] = mapped_column(index=True)
    verdict: Mapped[str] = mapped_column(String(10))


class ReviewLog(UserOwned, Base):
    """One FSRS review of a unit. `reviewed_at` is when the answer was submitted, also for a
    later override (plan D7): replay (T2.6) keeps the real gaps between reviews, and reads only
    the rows of each attempt's latest grade."""

    __tablename__ = "review_log"
    __table_args__ = (
        ForeignKeyConstraint(
            ["grade_id", "unit_id", "user_id"],
            ["grade_unit.grade_id", "grade_unit.unit_id", "grade_unit.user_id"],
            ondelete="NO ACTION",
        ),
        ForeignKeyConstraint(
            ["unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            ondelete="NO ACTION",
        ),
        CheckConstraint(one_of("facet", FACETS), name="facet_known"),
        CheckConstraint(f"rating IN ({', '.join(map(str, RATINGS))})", name="rating_known"),
        UniqueConstraint("grade_id", "unit_id", "facet"),
        Index(None, "user_id", "reviewed_at", "seq"),
        Index(None, "unit_id", "facet"),
    )

    unit_id: Mapped[uuid.UUID]
    facet: Mapped[str] = mapped_column(String(20), default="core", server_default="core")
    rating: Mapped[int] = mapped_column(SmallInteger)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grade_id: Mapped[uuid.UUID] = mapped_column(index=True)
    seq: Mapped[int] = _seq()


class MemoryState(UserOwned, Base):
    """FSRS state of one (unit, facet), mirroring `domain.scheduling.MemoryState`. A cache:
    changed on every review, rebuilt from review_log when needed (T2.6)."""

    __tablename__ = "memory_state"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            ondelete="NO ACTION",
        ),
        CheckConstraint(one_of("facet", FACETS), name="facet_known"),
        CheckConstraint(one_of("phase", PHASES), name="phase_known"),
        CheckConstraint("(phase = 'relearning') = (step IS NOT NULL)", name="step_when_relearning"),
        # user_id in the key: an upsert of another user's unit must not find this row and update
        # it in place; it tries to insert, and the composite key refuses (review 31074ea).
        UniqueConstraint("user_id", "unit_id", "facet"),
        Index(None, "user_id", "due"),
    )

    unit_id: Mapped[uuid.UUID]
    facet: Mapped[str] = mapped_column(String(20), default="core", server_default="core")
    phase: Mapped[str] = mapped_column(String(10))
    step: Mapped[int | None] = mapped_column(SmallInteger)
    stability: Mapped[float] = mapped_column(Float(precision=53))
    difficulty: Mapped[float] = mapped_column(Float(precision=53))
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_review: Mapped[datetime] = mapped_column(DateTime(timezone=True))
