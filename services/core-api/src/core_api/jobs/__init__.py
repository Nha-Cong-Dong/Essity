"""Background jobs inside core-api, on Procrastinate (ADR-0014).

The rest of the app uses two things only: `queue.enqueue_job` to add a job inside the current
transaction, and `handler.job_handler` (in `registry`) to declare what runs it. Procrastinate is
imported nowhere outside this package (tests/jobs/test_boundary.py). The worker is
`python -m core_api.jobs.worker`.
"""
