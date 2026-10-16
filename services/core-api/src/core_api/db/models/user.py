import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, CreatedAt

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_DAY_START_HOUR = 4  # Q12: a learning day starts at 04:00


class User(CreatedAt, Base):
    """An account (ADR-0014). Not `UserOwned`: it is the owner."""

    __tablename__ = "user"
    __table_args__ = (
        # Normalized in code (domain.email); the database refuses anything else, so two rows can
        # never differ only by case.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("day_start_hour BETWEEN 0 AND 23", name="day_start_hour_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)  # 320: longest valid address
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Empty for accounts that only sign in with Google (M5). argon2id hash otherwise (T1.7).
    password_hash: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), server_default=text(f"'{DEFAULT_TIMEZONE}'"))
    day_start_hour: Mapped[int] = mapped_column(
        SmallInteger, server_default=text(str(DEFAULT_DAY_START_HOUR))
    )
    # Per-user FSRS parameters once the optimizer has run (ADR-0009); empty = FSRS defaults.
    fsrs_params: Mapped[list[float] | None] = mapped_column(JSONB)
    fsrs_params_version: Mapped[int | None]
    # Empty = the user has not agreed to their data being used for evals.
    eval_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
