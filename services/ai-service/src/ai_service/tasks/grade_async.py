"""Grade an attempt from the queue (T4.19): `grade.requested.v1` in, a result file and
`grade.completed.v1` out. The path core-api takes when the synchronous call to /v1/grade failed
for a reason that may clear (T2.13), so the answer is graded once ai-service is back.

The request is a file written by core-api (the body of /v1/grade, claim-check: no answer travels
in an event); the result is a file too, `{"status": "graded", "response": <GradeResponse>}` or
`{"status": "failed", "failure": "invalid" | "disabled"}` (contracts/files/grade-result.v1).

Idempotent on the event (consumer.Handler): the result key and the id of the event sent derive
from the incoming event's id, and a result already written is only announced again, so a crash
between the file and the event never pays the model twice. Nothing here logs an answer.

Deferred, not failed: the storage not answering, the model unavailable, the audit trail not
writable. Failed (a result, not an exception): the request or the output can never be graded,
because asking again gives the same answer; core-api shows "Chấm lại" for those. A bug in this
code raises, and the consumer counts it towards the dead letter.
"""

import logging
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from redis import Redis
from sqlalchemy.orm import Session

from ai_service.api.grade import MAX_BODY_BYTES
from ai_service.clients.storage import (
    ObjectNotFound,
    ObjectStorage,
    ObjectTooLarge,
    StorageUnavailable,
)
from ai_service.db.session import SessionFactory
from ai_service.llm.client import AuditUnavailableError, LlmClient, LlmUnavailableError
from ai_service.messaging.consumer import Deferred, keys_belong_to_user
from ai_service.messaging.dead_letter import STREAM_MAXLEN
from ai_service.messaging.envelope import (
    Event,
    GradeCompleted,
    GradeCompletedEvent,
    GradeRequestedEvent,
    dump_event,
)
from ai_service.tasks.grade import GradeInvalidError, grade_answer
from ai_service.tasks.grade_models import GradeRequest

OUT_STREAM = "events.ai"
_NAMESPACE = uuid.UUID("5b1b6f0e-8c0e-4e5a-9a37-7a0e6d6f1c12")
_JSON = "application/json"

_log = logging.getLogger(__name__)


def completed_event_id(event_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"completed:{event_id}")


def result_key_for(event: GradeRequestedEvent) -> str:
    """Next to the request: `users/<user>/grading/<attempt>/result-<event>.json`."""
    directory = event.payload.request_key.rsplit("/", 1)[0]
    return f"{directory}/result-{event.event_id}.json"


class GradeAsync:
    """The handler of `grade.requested.v1`. `llm` is None when grading is disabled."""

    def __init__(
        self,
        *,
        storage: ObjectStorage,
        redis: Redis,
        llm: LlmClient | None,
        sessions: SessionFactory,
        stream: str = OUT_STREAM,
    ) -> None:
        self.storage, self.redis, self.llm = storage, redis, llm
        self.sessions, self.stream = sessions, stream

    def __call__(self, session: Session, event: Event) -> None:
        if not isinstance(event, GradeRequestedEvent):
            raise TypeError("GradeAsync handles grade.requested.v1 only")
        result_key = result_key_for(event)
        if not self._written(result_key):
            self._put(result_key, self._result(event))
        self._announce(event, result_key)

    def _written(self, key: str) -> bool:
        try:
            self.storage.get(key, max_bytes=MAX_BODY_BYTES)
        except ObjectNotFound:
            return False
        except ObjectTooLarge:
            return True
        except StorageUnavailable:
            raise Deferred from None
        return True

    def _result(self, event: GradeRequestedEvent) -> str:
        payload = event.payload
        directory = f"users/{event.user_id}/grading/{payload.attempt_id}/"
        # F2 again (the consumer already dead-letters a key of another user): the request must
        # be this attempt's own file.
        if not keys_belong_to_user(event) or not payload.request_key.startswith(directory):
            return _failed("invalid")
        try:
            raw = self.storage.get(payload.request_key, max_bytes=MAX_BODY_BYTES)
        except (ObjectNotFound, ObjectTooLarge):
            return _failed("invalid")
        except StorageUnavailable:
            raise Deferred from None
        try:
            request = GradeRequest.model_validate_json(raw)
        except ValidationError:  # its errors echo the answer: never logged
            return _failed("invalid")
        if request.user_id != event.user_id or request.attempt_id != payload.attempt_id:
            return _failed("invalid")
        if self.llm is None:
            return _failed("disabled")
        try:
            response = grade_answer(request, llm=self.llm, sessions=self.sessions)
        except GradeInvalidError:
            return _failed("invalid")
        except (LlmUnavailableError, AuditUnavailableError):
            raise Deferred from None
        return f'{{"status":"graded","response":{response.model_dump_json()}}}'

    def _put(self, key: str, body: str) -> None:
        try:
            self.storage.put(key, body.encode(), content_type=_JSON)
        except StorageUnavailable:
            raise Deferred from None

    def _announce(self, event: GradeRequestedEvent, result_key: str) -> None:
        completed = GradeCompletedEvent(
            event_id=completed_event_id(event.event_id),
            event_type="grade.completed.v1",
            schema_version=1,
            occurred_at=datetime.now(UTC),
            user_id=event.user_id,
            trace_context=event.trace_context,
            payload=GradeCompleted(attempt_id=event.payload.attempt_id, result_key=result_key),
        )
        self.redis.xadd(
            self.stream,
            {"envelope": dump_event(completed)},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )


def _failed(failure: str) -> str:
    _log.warning("async grade failed", extra={"outcome": failure})
    return f'{{"status":"failed","failure":"{failure}"}}'
