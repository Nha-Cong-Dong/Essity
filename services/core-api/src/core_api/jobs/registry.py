"""Every job handler, declared with `@job_handler("<kind>")`.

The API and the worker both import this module, so a kind is known on both sides: `enqueue_job`
refuses kinds missing here, and the worker would fail jobs whose kind it does not know.
"""

from core_api.jobs.handler import job_handler  # noqa: F401  # pyright: ignore[reportUnusedImport]

# send_email (T1.5) goes here.
