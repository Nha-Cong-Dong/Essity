"""`user.deleted.v1` (T6.3): core erased a user; ai-service erases what it holds of them.

Rows go in the consumer's transaction: `llm_call` before `pipeline_run` (the foreign key is
RESTRICT), then `llm_reservation`. The dead letter stream keeps envelopes with study content, so
every entry that mentions the user goes too (`purge_user`). `processed_event` stays: it holds
event ids only, no user and no content. Objects are core's to delete (ADR-0012: ai-service has no
delete right).

The user is `event.user_id`, never the payload (empty by contract). Handling it again, or for a
user ai-service never saw, deletes nothing and succeeds: core sends the event again on purpose to
sweep what a task still in flight wrote after the first one.
"""

import logging
from typing import Any, cast

from redis import Redis
from sqlalchemy import CursorResult, delete
from sqlalchemy.orm import Session

from ai_service.db.models import LlmCall, LlmReservation, PipelineRun
from ai_service.messaging.dead_letter import purge_user
from ai_service.messaging.envelope import Event, UserDeletedEvent

_log = logging.getLogger("ai_service.tasks")


class OnUserDeleted:
    def __init__(self, *, redis: Redis, dead_stream: str) -> None:
        self._redis = redis
        self._dead_stream = dead_stream

    def __call__(self, session: Session, event: Event) -> None:
        if not isinstance(event, UserDeletedEvent):
            raise TypeError("OnUserDeleted handles user.deleted.v1 only")
        user_id = event.user_id
        calls = cast(
            CursorResult[Any], session.execute(delete(LlmCall).where(LlmCall.user_id == user_id))
        ).rowcount
        runs = cast(
            CursorResult[Any],
            session.execute(delete(PipelineRun).where(PipelineRun.user_id == user_id)),
        ).rowcount
        session.execute(delete(LlmReservation).where(LlmReservation.user_id == user_id))
        # Redis is outside the transaction; deleting dead entries again is harmless.
        dead = purge_user(self._redis, dead_stream=self._dead_stream, user_id=user_id)
        _log.info(
            "user erased",
            extra={"event_id": str(event.event_id), "llm_calls": calls, "runs": runs, "dead": dead},
        )
