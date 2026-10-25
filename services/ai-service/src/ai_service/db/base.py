"""Declarative base for the tables of database `ai` (ADR-0007: one database per service)."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Every constraint gets a predictable name, so Alembic migrations can drop or alter it later.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


def one_of(column: str, values: frozenset[str]) -> str:
    """SQL for a CHECK that `column` is one of `values` (a CHECK, not a Postgres ENUM)."""
    return f"{column} IN ({', '.join(repr(value) for value in sorted(values))})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
