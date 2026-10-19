"""`enqueue_job`: add a job in the caller's transaction."""

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from core_api.jobs.app import deferrer
from core_api.jobs.handler import check_kind

_log = logging.getLogger("core_api.jobs")


def enqueue_job(session: Session, kind: str, payload: dict[str, Any]) -> None:
    """Add a job of `kind`, written in `session`'s transaction.

    The job exists only if that transaction commits: a route that fails after enqueueing
    leaves no job behind, and workers see the job once the route has committed. No second
    connection is opened. Raises `UnknownJobKind` for a kind without a handler and `TypeError`
    for a payload that is not JSON-serialisable, before anything is written.
    """
    # Imported here, not at the top: handler modules import this one to offer helpers such as
    # `enqueue_email`, so a top-level import would make a cycle (tests/jobs/test_boundary.py).
    import core_api.jobs.registry  # noqa: F401  # pyright: ignore[reportUnusedImport]

    check_kind(kind)
    json.dumps(payload)
    # The psycopg connection under the session, in the transaction the session has begun.
    connection = session.connection().connection.driver_connection
    job_id = deferrer.configure_task(name=kind, connection=connection).defer(payload=payload)
    _log.info("job enqueued", extra={"job_kind": kind, "job_id": job_id})
