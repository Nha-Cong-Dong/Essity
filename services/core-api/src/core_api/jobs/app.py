"""The Procrastinate apps and the retry policy shared by every job."""

import procrastinate
from procrastinate.jobs import Job
from sqlalchemy.engine import make_url

MAX_ATTEMPTS = 5
FIRST_RETRY_SECONDS = 10
RETRY_FACTOR = 3


class Backoff(procrastinate.RetryStrategy):
    """Retry any exception after 10 s, 30 s, 90 s, 270 s: five attempts in all.

    `RetryStrategy` decides whether to retry (attempts left, exception types); only the delay
    is ours, since its own exponential formula cannot start at 10 s and triple.
    """

    def get_retry_decision(
        self, *, exception: BaseException, job: Job
    ) -> procrastinate.RetryDecision | None:
        if super().get_retry_decision(exception=exception, job=job) is None:
            return None
        # job.attempts counts the runs before this one: 0 on the first failure.
        delay = FIRST_RETRY_SECONDS * RETRY_FACTOR**job.attempts
        return procrastinate.RetryDecision(retry_in={"seconds": delay})


# max_attempts counts retries; after the last one the job stays in the table as `failed`.
RETRY = Backoff(max_attempts=MAX_ATTEMPTS - 1)

# Where handlers are registered and what the worker runs. Its connector gets a real pool only in
# the worker (worker.open_app); the API never opens it.
app = procrastinate.App(connector=procrastinate.PsycopgConnector())

# Defers jobs by name on a connection the caller passes (queue.enqueue_job), so it never opens
# a pool or a connection of its own. Separate from `app`: once the worker opens `app`, its
# connector is async only, and a handler may enqueue further jobs.
deferrer = procrastinate.App(connector=procrastinate.SyncPsycopgConnector())


def libpq_conninfo(database_url: str) -> str:
    """`postgresql+psycopg://...` (SQLAlchemy) -> `postgresql://...` (libpq, psycopg_pool)."""
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)
