from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned


class AuthSession(UserOwned, Base):
    """A signed-in session (ADR-0014, ADR-0020): only the SHA-256 of its token is stored."""

    __tablename__ = "auth_session"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # hex SHA-256
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # sliding (30 days)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(256))  # never logged
