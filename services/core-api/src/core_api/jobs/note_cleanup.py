"""The `note_cleanup` job (T4.13b): note files whose upload URL was signed long ago and that no
confirmed session holds are deleted, file first and then row.

`note_cleanup_after_seconds` is at least twice the URL's life (config), so no URL still works
when its row goes. A row a confirm is deciding about is skipped (SKIP LOCKED), not waited for.
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
from core_api.db.models import NoteUpload
from core_api.jobs.handler import periodic_job

NOTE_CLEANUP = "note_cleanup"
BATCH = 500

_log = logging.getLogger("core_api.jobs")


def delete_abandoned_notes(
    session: Session, storage: ObjectStorage, now: datetime, older_than: timedelta
) -> int:
    """Delete up to BATCH pending notes signed before `now - older_than`, their files first;
    return how many. Every user's: a system job, not a user's request. StorageUnavailableError
    stops it, the rows not yet cleared left in place."""
    due = session.scalars(
        select(NoteUpload)
        .where(NoteUpload.presigned_at < now - older_than)
        .order_by(NoteUpload.presigned_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    deleted = 0
    for row in due:
        storage.delete(row.object_key)
        session.delete(row)
        session.flush()
        deleted += 1
    return deleted


@periodic_job(NOTE_CLEANUP, cron="45 * * * *")
def note_cleanup_job(payload: dict[str, Any]) -> None:
    settings = get_settings()
    storage = S3Storage.from_settings(settings)
    older_than = timedelta(seconds=settings.note_cleanup_after_seconds)
    with Session(get_engine()) as session:
        try:
            deleted = delete_abandoned_notes(session, storage, datetime.now(UTC), older_than)
        except StorageUnavailableError:
            session.commit()  # what was cleared before the store went down stays cleared
            raise
        session.commit()
    _log.info("abandoned notes deleted", extra={"deleted_count": deleted})
