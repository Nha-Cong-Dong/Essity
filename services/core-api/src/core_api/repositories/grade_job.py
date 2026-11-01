"""Attempts whose grading went to the queue (T4.19). One row per attempt."""

import uuid
from datetime import datetime

from core_api.db.models import GradeJob
from core_api.db.models.grade_job import GRADE_JOB_FAILURES
from core_api.repositories.base import UserScopedRepository


class GradeJobRepository(UserScopedRepository[GradeJob]):
    model = GradeJob

    def for_attempt(self, attempt_id: uuid.UUID) -> GradeJob | None:
        return self.session.scalars(
            self._select().where(GradeJob.attempt_id == attempt_id)
        ).one_or_none()

    def queue(self, attempt_id: uuid.UUID, request_key: str, now: datetime) -> GradeJob:
        """The attempt is waiting for ai-service: a new row, or a failed one asked again."""
        job = self.for_attempt(attempt_id)
        if job is None:
            job = self.add(
                GradeJob(
                    attempt_id=attempt_id,
                    status="queued",
                    failure=None,
                    request_key=request_key,
                    updated_at=now,
                )
            )
        else:
            job.status, job.failure = "queued", None
            job.request_key, job.updated_at = request_key, now
        self.session.flush()
        return job

    def fail(self, attempt_id: uuid.UUID, failure: str, now: datetime) -> None:
        """The queued grading can never be a grade: the screen offers "Chấm lại"."""
        job = self.for_attempt(attempt_id)
        if job is not None:
            job.status, job.failure, job.updated_at = "failed", failure, now
            self.session.flush()

    def done(self, attempt_id: uuid.UUID) -> None:
        """A grade exists: the row has nothing left to say."""
        job = self.for_attempt(attempt_id)
        if job is not None:
            self.session.delete(job)
            self.session.flush()

    def settle_practice(
        self, attempt_id: uuid.UUID, grading: str, failure: str | None, now: datetime
    ) -> None:
        """Keep a practice attempt's row true to its grading outcome (T8.4b, US-05 AC14).

        `graded` ends the row; `pending` queues it (a practice job holds no file: the answer is in
        the attempt, `request_key` is empty); `failed` keeps it as `failed`, with a failure code
        the table knows. `in_progress` changes nothing."""
        if grading == "graded":
            self.done(attempt_id)
        elif grading == "pending":
            self.queue(attempt_id, "", now)
        elif grading == "failed":
            self.queue(attempt_id, "", now)
            self.fail(attempt_id, failure if failure in GRADE_JOB_FAILURES else "invalid", now)
