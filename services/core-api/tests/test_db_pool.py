"""Review T2.13 🟡2 (plan 🟡8): the connection pool is sized in the settings, not left to
SQLAlchemy's default 5 + 10. A grading holds one connection for up to ~20 s (risk: T2.11)."""

from sqlalchemy.pool import QueuePool

from core_api.config import Settings
from core_api.db.engine import create_db_engine, engine_for


def test_t213_the_pool_is_sized_by_the_settings() -> None:
    settings = Settings(db_pool_size=7, db_max_overflow=3)  # pyright: ignore[reportCallIssue]
    pool = engine_for(settings).pool
    assert isinstance(pool, QueuePool)
    assert (pool.size(), pool._max_overflow) == (7, 3)  # pyright: ignore[reportPrivateUsage]


def test_t213_the_default_pool_is_explicit() -> None:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    assert (settings.db_pool_size, settings.db_max_overflow) == (10, 10)


def test_t213_an_engine_without_settings_keeps_its_pool_arguments() -> None:
    engine = create_db_engine("postgresql+psycopg://u:p@127.0.0.1/x", pool_size=2, max_overflow=0)
    pool = engine.pool
    assert isinstance(pool, QueuePool) and pool.size() == 2
