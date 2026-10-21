"""The `purge_unverified` job (T1.9): accounts never verified are deleted after 7 days.

ADR-0020 §4: an address someone typed but never confirmed should not hold an account, or its
data, for long. The delete is outright, and the database cascades it to every row that belongs
to the user (tokens, sessions, subjects...). A verified account is never touched here.

Runs every hour. Running twice is harmless: the second run finds nothing to delete.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from core_api.db.engine import get_engine
from core_api.db.models import User
from core_api.jobs.handler import periodic_job

PURGE_UNVERIFIED = "purge_unverified"
UNVERIFIED_LIFETIME = timedelta(days=7)

_log = logging.getLogger("core_api.jobs")


def purge_unverified(session: Session, now: datetime) -> int:
    """Delete accounts still unverified `UNVERIFIED_LIFETIME` after sign-up; return how many."""
    deleted = session.scalars(
        delete(User)
        .where(User.email_verified_at.is_(None), User.created_at < now - UNVERIFIED_LIFETIME)
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    return len(deleted.all())


@periodic_job(PURGE_UNVERIFIED, cron="0 * * * *")
def purge_unverified_job(payload: dict[str, Any]) -> None:
    with Session(get_engine()) as session:
        deleted = purge_unverified(session, datetime.now(UTC))
        session.commit()
    _log.info("unverified accounts purged", extra={"deleted_count": deleted})
