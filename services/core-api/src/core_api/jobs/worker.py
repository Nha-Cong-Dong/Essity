"""The job worker: `python -m core_api.jobs.worker` (Compose service `core-worker`).

Runs one job at a time until SIGTERM or SIGINT. On either, it takes no new job and waits up to
`SHUTDOWN_GRACE_SECONDS` for the running one; a job still running then is released, to be
retried by the next worker (keep Compose's `stop_grace_period` above that). A worker killed
outright leaves its job `doing`: the next worker to start finds it through the dead worker's
stale heartbeat and retries it.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from typing import Any, Unpack

import procrastinate
from procrastinate.app import WorkerOptions

import core_api.jobs.registry  # noqa: F401  # pyright: ignore[reportUnusedImport]  # registers kinds
from core_api.config import get_settings
from core_api.jobs.app import app, libpq_conninfo
from core_api.logging import configure_logging
from core_api.telemetry import configure_tracing

SERVICE = "core-worker"
SHUTDOWN_GRACE_SECONDS = 20.0

_log = logging.getLogger("core_api.jobs")


@asynccontextmanager
async def open_app(conninfo: str) -> AsyncGenerator[procrastinate.App]:
    """The jobs app, connected to `conninfo` with a pool of its own, for running workers."""
    # Few connections for one job at a time: fetch, heartbeat, abort polling. LISTEN uses a
    # connection of its own, outside the pool.
    connector = procrastinate.PsycopgConnector(conninfo=conninfo, min_size=1, max_size=4)
    with app.replace_connector(connector):
        async with app.open_async():
            yield app


async def run_workers(conninfo: str, count: int = 1, **options: Unpack[WorkerOptions]) -> None:
    """Run `count` workers on one pool until stopped or, with `wait=False`, out of due jobs."""
    async with open_app(conninfo) as jobs_app:
        await _retry_stalled_jobs(jobs_app)
        workers: list[Coroutine[Any, Any, None]] = []
        for i in range(count):
            options["name"] = f"{SERVICE}-{i}"
            workers.append(jobs_app.run_worker_async(**options))
        await asyncio.gather(*workers)


async def _retry_stalled_jobs(jobs_app: procrastinate.App) -> None:
    """Put back jobs left `doing` by workers that died without releasing them."""
    for job in await jobs_app.job_manager.get_stalled_jobs():
        await jobs_app.job_manager.retry_job(job)
        _log.warning("stalled job requeued", extra={"job_kind": job.task_name, "job_id": job.id})


def run(main: Coroutine[Any, Any, None]) -> None:
    # psycopg's async connections need a selector event loop; Windows defaults to Proactor.
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(main, loop_factory=factory)


def main() -> None:
    settings = get_settings()
    configure_logging(SERVICE, settings.log_level)
    provider = configure_tracing(SERVICE)
    conninfo = libpq_conninfo(settings.database_url.get_secret_value())
    _log.info("worker starting")
    try:
        run(run_workers(conninfo, shutdown_graceful_timeout=SHUTDOWN_GRACE_SECONDS))
    finally:
        provider.shutdown()  # export the last spans
        _log.info("worker stopped")


if __name__ == "__main__":
    main()
