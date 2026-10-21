from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned


class Baseline(UserOwned, Base):
    """Where the user started (US-11): GPA and days of revision before last term's exams.

    One per user, entered once and editable for 7 days (domain.baseline). GPA is personal data:
    never logged (ADR-0013).
    """

    __tablename__ = "baseline"
    __table_args__ = (
        UniqueConstraint("user_id"),
        CheckConstraint("gpa_before BETWEEN 0 AND 4", name="gpa_before_range"),
        CheckConstraint("gpa_after BETWEEN 0 AND 4", name="gpa_after_range"),
        CheckConstraint("prior_ready_days BETWEEN 0 AND 365", name="prior_ready_days_range"),
        # "Don't remember" is stored as an estimate of 0 days (AC1).
        CheckConstraint(
            "NOT prior_days_unknown OR prior_ready_days = 0", name="unknown_days_are_zero"
        ),
    )

    gpa_before: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    prior_ready_days: Mapped[int] = mapped_column(SmallInteger)
    prior_days_unknown: Mapped[bool] = mapped_column(Boolean)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_late: Mapped[bool] = mapped_column(Boolean)
    # End-of-term GPA, asked after the last exam (T5.7).
    gpa_after: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
