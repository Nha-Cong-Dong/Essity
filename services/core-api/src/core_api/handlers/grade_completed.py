"""`grade.completed.v1` (T4.19, US-05): ai-service's result for a grading that went to the queue.

The consumer has claimed the event (so it is handled once) and checked that the result key is under
the event's user (F2); here the attempt must be that user's too, the key must be the attempt's own
directory, and a grade that exists already ends it (the synchronous path, or a first delivery that
committed). The result file is read, checked against the units of the question exactly like a
synchronous answer (`check_response`, R03/R41 layer 2) and written by the same `record_grade`.

- A result that can never be a grade (a failed result, a file that is missing or breaks the
  contract, a unit set that changed, a refused answer) marks the job `failed`: the screen offers
  "Chấm lại". Nothing is written.
- The storage not answering, or the attempt's grading lock held by a request, raises: the consumer
  retries with backoff.

Logs hold ids and reasons, never the answer or the file (ADR-0013).
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core_api.clients.grade_contract import GRADE_RESULT, FailedResult
from core_api.clients.storage import ObjectStorage, StorageUnavailableError
from core_api.db.models import Attempt, User
from core_api.domain.grading import ResponseRefused, check_response
from core_api.grading import record_grade, units_of
from core_api.messaging.envelope import Event, GradeCompletedEvent
from core_api.repositories.grade_job import GradeJobRepository
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import AttemptRepository, GradeRepository, UnitsMismatchError
from core_api.repositories.subject import SubjectNotFoundError

_log = logging.getLogger("core_api.handlers")
# A result is a few kilobytes; ai-service's request limit is 512 KB.
MAX_RESULT_BYTES = 512 * 1024


class GradingBusyError(Exception):
    """A request holds the attempt's grading lock: try again after the backoff."""


class OnGradeCompleted:
    def __init__(
        self,
        storage: ObjectStorage,
        *,
        environment: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.storage, self.environment, self.clock = storage, environment, clock

    def __call__(self, session: Session, event: Event) -> None:
        assert isinstance(event, GradeCompletedEvent)
        attempt_id, key = event.payload.attempt_id, event.payload.result_key
        extra = {"event_id": str(event.event_id), "attempt_id": str(attempt_id)}
        user = session.get(User, event.user_id)
        attempt = None if user is None else AttemptRepository(session, user.id).get(attempt_id)
        if user is None or attempt is None or attempt.status != "submitted":
            _log.warning("grade result ignored", extra=extra | {"found": attempt is not None})
            return
        if not key.startswith(f"users/{user.id}/grading/{attempt_id}/"):
            _log.warning("grade result refused", extra=extra)
            return
        grades = GradeRepository(session, user.id)
        if not grades.try_lock_attempt(attempt_id):
            raise GradingBusyError
        jobs = GradeJobRepository(session, user.id)
        job = jobs.for_attempt(attempt_id)
        files = [key] if job is None else [key, job.request_key]
        if grades.latest_for_attempt(attempt_id) is not None:
            jobs.done(attempt_id)
            return self._delete(files)

        failure = self._failure(session, user, attempt, key, extra)
        if failure is None:
            jobs.done(attempt_id)
        else:
            jobs.fail(attempt_id, failure, self.clock())
        self._delete(files)

    def _failure(
        self,
        session: Session,
        user: User,
        attempt: Attempt,
        key: str,
        extra: dict[str, str],
    ) -> str | None:
        """Record the grade the result holds; the failure it ends with otherwise."""
        raw = self.storage.read(key, max_bytes=MAX_RESULT_BYTES)  # raises: retried
        if raw is None:
            _log.warning("grade result missing", extra=extra)
            return "invalid"
        try:
            result = GRADE_RESULT.validate_json(raw)
        except ValidationError:  # its errors echo the input: never logged
            _log.error("grade result refused", extra=extra | {"reason": "schema"})
            return "invalid"
        if isinstance(result, FailedResult):
            _log.warning("grade result failed", extra=extra | {"reason": result.failure})
            return result.failure
        question = QuestionRepository(session, user.id).get(attempt.question_id)
        assert question is not None  # an attempt's question is never deleted (foreign key)
        try:
            checked = check_response(
                result.response,
                units=units_of(session, user.id, question.id),
                environment=self.environment,
            )
        except ResponseRefused as refused:
            _log.error("grade result refused", extra=extra | {"reason": f"response_{refused}"})
            return "invalid"
        try:
            with session.begin_nested():
                record_grade(session, user, attempt, checked)
        except (UnitsMismatchError, SubjectNotFoundError):
            _log.error("grade result refused", extra=extra | {"reason": "units_changed"})
            return "invalid"
        return None

    def _delete(self, keys: list[str]) -> None:
        """The request holds the answer: it goes with the job. Best effort, never a failure."""
        for key in keys:
            try:
                self.storage.delete(key)
            except StorageUnavailableError:
                _log.warning("grade file not deleted")
