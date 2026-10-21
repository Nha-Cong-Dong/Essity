"""Fixtures for tests that commit jobs and run real workers on the test database."""

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, text

from core_api.jobs.app import app, libpq_conninfo
from core_api.jobs.worker import run, run_workers


@pytest.fixture
def clean_jobs(engine: Engine) -> Iterator[None]:
    """Empty the job tables around each test: workers only see committed jobs.

    Test modules that run jobs use it with `pytestmark = pytest.mark.usefixtures("clean_jobs")`.
    """

    def clean() -> None:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM procrastinate_jobs"))
            connection.execute(text("DELETE FROM procrastinate_workers"))

    clean()
    yield
    clean()


@pytest.fixture
def work(test_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Run workers until no job is due, then return.

    Without periodic tasks: a worker defers any periodic job due in the last 10 minutes, so the
    hourly purge would show up in tests run just after the hour. Tests defer it by hand instead.
    """
    monkeypatch.setattr(app, "periodic_registry", type(app.periodic_registry)())
    conninfo = libpq_conninfo(test_database_url)

    def work(count: int = 1) -> None:
        run(
            run_workers(
                conninfo, count, wait=False, install_signal_handlers=False, listen_notify=False
            )
        )

    return work
