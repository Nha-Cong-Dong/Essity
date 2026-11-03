"""The `erase_user_sweep` job (T6.3): the second pass of erasing a user.

`erase-user` queues it in the same transaction as the `user.deleted.v1` event, to run 20 minutes
later (`delete_user.SWEEP_DELAY`). By then whatever was in flight when the user row went has
landed: it clears that, and sends the event again so ai-service deletes what it wrote since.

It does not queue itself again. If the user row exists when it runs (the erase was undone by a
restore, or a wrong id), it does nothing and fails the job loudly instead of deleting a living
user's files. The payload is the user's id only (ADR-0018).
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core_api.clients.redis import get_redis
from core_api.clients.storage import ObjectStorage, S3Storage
from core_api.config import get_settings
from core_api.db.engine import get_engine
from core_api.domain.delete_user import ERASE_USER_SWEEP, sweep_user
from core_api.jobs.handler import job_handler

_log = logging.getLogger("core_api.jobs")


def _storage() -> ObjectStorage:
    return S3Storage.from_settings(get_settings())


@job_handler(ERASE_USER_SWEEP)
def erase_user_sweep(payload: dict[str, Any]) -> None:
    result = sweep_user(
        app_engine=get_engine(),
        storage=_storage(),
        redis=get_redis(),
        user_id=uuid.UUID(payload["user_id"]),
        now=datetime.now(UTC),
    )
    _log.info(
        "erase sweep done",
        extra={
            "deleted_count": result.outbox_rows
            + result.objects
            + result.dead_entries
            + result.stream_entries
        },
    )
