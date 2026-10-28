import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, one_of

GRADE_JOB_STATUSES = frozenset({"queued", "failed"})
# Why a queued grading ended without a grade; the same codes as `AttemptView.failure`.
GRADE_JOB_FAILURES = frozenset({"disabled", "invalid", "unavailable"})


class GradeJob(UserOwned, Base):
    """An attempt whose grading went to the queue (T4.19, ADR-0006): `grade.requested.v1` was sent
    because the synchronous call failed for a reason that may clear.

    One row per attempt. `queued` shows as "đang chấm" until a grade exists; `failed` (the result
    can never be a grade) shows as "Chấm lại". A grade written wins over the row, which is
    deleted with it. The row holds no answer: the request and the result are files.
    """

    __tablename__ = "grade_job"
    __table_args__ = (
        ForeignKeyConstraint(
            ["attempt_id", "user_id"],
            ["attempt.id", "attempt.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("attempt_id"),
        CheckConstraint(one_of("status", GRADE_JOB_STATUSES), name="status_known"),
        CheckConstraint(
            f"failure IS NULL OR {one_of('failure', GRADE_JOB_FAILURES)}", name="failure_known"
        ),
        CheckConstraint("(status = 'failed') = (failure IS NOT NULL)", name="failed_iff_failure"),
    )

    attempt_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(10))
    failure: Mapped[str | None] = mapped_column(String(12))
    # The request file, deleted with the result once the job is over (it holds the answer).
    request_key: Mapped[str] = mapped_column(String(1024))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
