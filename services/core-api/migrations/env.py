"""Alembic environment for core-api.

The URL is `sqlalchemy.url` when a caller sets it (the tests do), otherwise CORE_DATABASE_URL.
Autogenerate compares against `Base.metadata`; every model must be imported in
`core_api.db.models` for it to be seen. Procrastinate's tables are not models and are skipped.
"""

import logging

from alembic import context
from sqlalchemy import create_engine, pool

import core_api.db.models  # noqa: F401  # pyright: ignore[reportUnusedImport]  # registers models
from core_api.config import DatabaseSettings
from core_api.db.base import Base

target_metadata = Base.metadata

# From the command line nothing has configured logging yet: show Alembic's progress. Inside the
# app or the tests, leave their logging alone (see alembic.ini).
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-5.5s [%(name)s] %(message)s")


def database_url() -> str:
    return context.config.get_main_option("sqlalchemy.url") or (
        DatabaseSettings().database_url.get_secret_value()  # pyright: ignore[reportCallIssue]
    )


def include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """Leave Procrastinate's objects out of autogenerate: migration 0002 creates them from SQL.

    Of those objects autogenerate only compares tables (and their indexes); it ignores
    functions, and enum types unless a model uses them.
    """
    return not (type_ == "table" and name is not None and name.startswith("procrastinate_"))


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, include_name=include_name
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
