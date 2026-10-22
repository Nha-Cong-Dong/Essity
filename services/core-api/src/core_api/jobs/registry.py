"""Every job handler, declared with `@job_handler("<kind>")`.

The API and the worker both import this module, so a kind is known on both sides: `enqueue_job`
refuses kinds missing here, and the worker would fail jobs whose kind it does not know.
"""

# Modules that declare handlers; importing them registers their kinds.
from core_api.jobs import (
    job_health,  # noqa: F401  # pyright: ignore[reportUnusedImport]
    purge_unverified,  # noqa: F401  # pyright: ignore[reportUnusedImport]
    send_email,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from core_api.jobs.handler import job_handler  # noqa: F401  # pyright: ignore[reportUnusedImport]
