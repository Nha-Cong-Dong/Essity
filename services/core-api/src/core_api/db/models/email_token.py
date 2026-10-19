from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned
from core_api.domain.auth.tokens import TokenPurpose


class EmailToken(UserOwned, Base):
    """A one-time token from an email link (ADR-0014): only its SHA-256 is stored."""

    __tablename__ = "email_token"
    __table_args__ = (
        CheckConstraint(
            "purpose IN (" + ", ".join(f"'{purpose}'" for purpose in TokenPurpose) + ")",
            name="purpose_known",
        ),
    )

    purpose: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # hex SHA-256
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
