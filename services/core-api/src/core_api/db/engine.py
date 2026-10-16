"""The database engine: one connection pool per process (ADR-0005: synchronous, psycopg 3)."""

from functools import lru_cache

import sqlalchemy
from opentelemetry.instrumentation.sqlalchemy import (  # pyright: ignore[reportMissingTypeStubs]
    SQLAlchemyInstrumentor,
)

from core_api.config import get_settings

# Instrument once per process, globally: every engine created afterwards gets one span per
# query, with the SQL text (placeholders, not values). Instrumenting a single engine instead
# only works for the first one; later calls are refused with a warning.
_instrumentor = SQLAlchemyInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument(enable_commenter=False)


def create_db_engine(url: str) -> sqlalchemy.Engine:
    # Looked up on the module at call time: the instrumentation replaces it there.
    # pre_ping replaces connections the server closed (restart, idle timeout) before use.
    return sqlalchemy.create_engine(url, pool_pre_ping=True)


@lru_cache
def get_engine() -> sqlalchemy.Engine:
    return create_db_engine(get_settings().database_url.get_secret_value())
