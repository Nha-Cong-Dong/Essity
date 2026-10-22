"""Declarative base for every core-api table (ADR-0008)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, MetaData, event, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, declared_attr, mapped_column
from sqlalchemy.orm.attributes import instance_state

# Every constraint gets a predictable name, so Alembic migrations can drop or alter it later.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


def one_of(column: str, values: frozenset[str]) -> str:
    """SQL for a CHECK that `column` is one of `values`: a CHECK, not a Postgres ENUM, so adding
    a value later is a migration that swaps the CHECK."""
    return f"{column} IN ({', '.join(repr(value) for value in sorted(values))})"


class OwnerChangeError(Exception):
    """A row of user data would move to another user."""


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserOwned(CreatedAt):
    """Columns of every table that holds a user's data.

    Read and write these tables only through a `UserScopedRepository`, which always filters by
    `user_id`. Deleting a user deletes their rows. A saved row never changes owner: the session
    refuses to write a changed `user_id` (`_refuse_owner_change`).
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        # active_history: keep the old value when user_id is set, even on an expired object, so
        # the flush check below always sees what it is replacing.
        return mapped_column(
            ForeignKey("user.id", ondelete="CASCADE"), index=True, active_history=True
        )


@event.listens_for(Session, "before_flush")
def _refuse_owner_change(session: Session, flush_context: Any, instances: Any) -> None:
    """Refuse to flush a saved row of user data whose `user_id` was changed, by any code path.

    Covers the ORM only; raw SQL `UPDATE`s are covered by row-level security in M6.
    """
    for obj in session.dirty:
        if isinstance(obj, UserOwned):
            history = instance_state(obj).attrs.user_id.history
            if history.deleted and history.added and history.deleted[0] != history.added[0]:
                raise OwnerChangeError(f"{type(obj).__name__} {obj.id} cannot change owner")
