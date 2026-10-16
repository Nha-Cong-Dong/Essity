"""Declarative base for every core-api table (ADR-0008)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Every constraint gets a predictable name, so Alembic migrations can drop or alter it later.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserOwned(CreatedAt):
    """Columns of every table that holds a user's data.

    Read and write these tables only through a `UserScopedRepository`, which always filters by
    `user_id`. Deleting a user deletes their rows.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
