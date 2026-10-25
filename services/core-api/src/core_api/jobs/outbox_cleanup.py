"""The `outbox_cleanup` job (T4.2, plan E8): outbox rows sent more than 7 days ago are deleted.

A sent row is history: the event is in Redis, and consumers dedupe by `event_id`. Seven days
leave time to look into a problem. An unsent row is never deleted here, however old: it is an
event still owed, and job_health reports it (`outbox_unsent_stale`).

Runs every hour. Running twice is harmless: the second run finds nothing to delete.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from core_api.db.engine import get_engine
from core_api.db.models import Outbox
from core_api.jobs.handler import periodic_job

OUTBOX_CLEANUP = "outbox_cleanup"
SENT_KEPT_FOR = timedelta(days=7)

_log = logging.getLogger("core_api.jobs")


def delete_sent_outbox(session: Session, now: datetime) -> int:
    """Delete rows sent before `now - SENT_KEPT_FOR`; return how many."""
    deleted = session.scalars(
        delete(Outbox)
        # NULL < anything is not true: an unsent row never matches.
        .where(Outbox.sent_at < now - SENT_KEPT_FOR)
        .returning(Outbox.id)
        .execution_options(synchronize_session=False)
    )
    return len(deleted.all())


@periodic_job(OUTBOX_CLEANUP, cron="30 * * * *")
def outbox_cleanup_job(payload: dict[str, Any]) -> None:
    with Session(get_engine()) as session:
        deleted = delete_sent_outbox(session, datetime.now(UTC))
        session.commit()
    _log.info("sent outbox rows deleted", extra={"deleted_count": deleted})
