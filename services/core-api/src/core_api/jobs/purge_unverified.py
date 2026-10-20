from datetime import datetime, timedelta

from sqlalchemy.orm import Session

PURGE_UNVERIFIED = "purge_unverified"
UNVERIFIED_LIFETIME = timedelta(days=7)


def purge_unverified(session: Session, now: datetime) -> int:
    return 0
