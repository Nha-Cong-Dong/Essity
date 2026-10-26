"""The `document_cleanup` job (T4.5, plan R1, R2): uploads never confirmed, or refused, are
deleted, file first and then row, once their last URL is long dead.

`document_cleanup_after_seconds` is at least twice the URL's life (config), so no URL still
works when its row goes: a PUT after that would store a file nothing accounts for. A row being
confirmed is skipped (SKIP LOCKED), not waited for; the next run takes it if it is still due.
If the store does not answer, the run stops and keeps the rows it had not cleared.

Runs every hour; running twice is harmless.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.clients.storage import ObjectStorage, S3Storage, StorageUnavailableError
from core_api.config import get_settings
from core_api.db.engine import get_engine
from core_api.db.models import Document
from core_api.jobs.handler import periodic_job

DOCUMENT_CLEANUP = "document_cleanup"
BATCH = 500

_log = logging.getLogger("core_api.jobs")


def delete_abandoned_uploads(
    session: Session, storage: ObjectStorage, now: datetime, older_than: timedelta
) -> int:
    """Delete up to BATCH documents not uploaded whose URL was signed before `now - older_than`,
    their files first; return how many. Every user's: a system job, not a user's request.
    StorageUnavailableError stops it, the rows not yet cleared left in place (the caller's
    commit keeps those that were)."""
    due = session.scalars(
        select(Document)
        .where(Document.status != "uploaded", Document.presigned_at < now - older_than)
        .order_by(Document.presigned_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    deleted = 0
    for document in due:
        storage.delete(document.object_key)
        session.delete(document)
        session.flush()
        deleted += 1
    return deleted


@periodic_job(DOCUMENT_CLEANUP, cron="15 * * * *")
def document_cleanup_job(payload: dict[str, Any]) -> None:
    settings = get_settings()
    storage = S3Storage.from_settings(settings)
    older_than = timedelta(seconds=settings.document_cleanup_after_seconds)
    with Session(get_engine()) as session:
        try:
            deleted = delete_abandoned_uploads(session, storage, datetime.now(UTC), older_than)
        except StorageUnavailableError:
            session.commit()  # what was cleared before the store went down stays cleared
            raise
        session.commit()
    _log.info("abandoned uploads deleted", extra={"deleted_count": deleted})
