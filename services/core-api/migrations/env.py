"""Alembic environment for core-api.

The URL is `sqlalchemy.url` when a caller sets it (the tests do), otherwise CORE_DATABASE_URL.
Autogenerate compares against `Base.metadata`; every model must be imported in
`core_api.db.models` for it to be seen.
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


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
