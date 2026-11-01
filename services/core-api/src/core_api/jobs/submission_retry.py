"""The `submission_retry` job (T7.8b, US-02b AC10): a submission parked as `pending_ai` because
the model was unavailable (`submission.failed.v1`, reason `llm_unavailable`) is handed to
ai-service again, with a growing delay and a bound.

- Due: `pending_ai` with `next_attempt_at` empty or past. Each is locked (SKIP LOCKED, so two
  workers never take the same one), set back to `queued`, counted in `retry_count`, given the
  next delay in `next_attempt_at` and sent again as `submission.created.v1` (same submission id,
  a new event id). If ai-service fails again it parks the row again and the delay applies.
- Bound: after MAX_RETRIES attempts a still-parked submission ends as `failed`. Manual work in
  the session stays open all the while (AC10).
- Idempotent: a repeat run finds the rows already `queued`, or not yet due, and does nothing. A
  result that lands anyway is written once (draft_key), and an ended submission is never revived.
- A submission whose files, subject or account are gone cannot be sent (a deleted account's notes
  never go to the model again): it ends as `failed`.

Logs hold ids and counts, never a key (ADR-0013). Runs every 10 minutes.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core_api.db.engine import get_engine
from core_api.db.models import NoteFile, StudySession, Submission, User
from core_api.jobs.handler import periodic_job
from core_api.messaging.envelope import SubmissionCreated, SubmissionFile
from core_api.messaging.outbox import enqueue_event
from core_api.repositories.subject import SubjectRepository

SUBMISSION_RETRY = "submission_retry"
MAX_RETRIES = 6
BATCH = 50
FIRST_DELAY = timedelta(minutes=15)
MAX_DELAY = timedelta(hours=6)

_log = logging.getLogger("core_api.jobs")


def delay_after(attempts: int) -> timedelta:
    """The wait after the `attempts`-th retry (1-based): 15 min, 30, 60 ... capped at 6 h."""
    return min(FIRST_DELAY * 2 ** max(attempts - 1, 0), MAX_DELAY)


def _end(row: Submission, now: datetime) -> None:
    row.status = "failed"
    row.finished_at = now
    row.next_attempt_at = None


def retry_pending_ai(session: Session, now: datetime) -> dict[str, int]:
    """Re-send up to BATCH due submissions and end the spent ones; return the counts."""
    due = session.scalars(
        select(Submission)
        .where(
            Submission.status == "pending_ai",
            or_(Submission.next_attempt_at.is_(None), Submission.next_attempt_at <= now),
        )
        .order_by(Submission.created_at, Submission.id)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    counts = {"retried": 0, "exhausted": 0, "unsendable": 0}
    for row in due:
        if row.retry_count >= MAX_RETRIES:
            _end(row, now)
            counts["exhausted"] += 1
            continue
        study = session.get(StudySession, row.session_id)
        files = _files(session, row)
        user = session.get(User, row.user_id)
        gone = user is None or user.deleted_at is not None
        if (
            gone
            or study is None
            or study.user_id != row.user_id
            or SubjectRepository(session, row.user_id).get(study.subject_id) is None
            or not files
        ):
            _end(row, now)
            counts["unsendable"] += 1
            continue
        row.retry_count += 1
        row.status = "queued"
        row.started_at = None
        row.next_attempt_at = now + delay_after(row.retry_count)
        enqueue_event(
            session,
            SubmissionCreated(
                submission_id=row.id,
                study_session_id=row.session_id,
                subject_id=study.subject_id,
                file_keys=files,
                context_key=_context_key(row.user_id, row.session_id, row.id),
            ),
            user_id=row.user_id,
            now=now,
        )
        counts["retried"] += 1
    session.flush()
    return counts


def _context_key(user_id: uuid.UUID, session_id: uuid.UUID, submission_id: uuid.UUID) -> str:
    return f"users/{user_id}/sessions/{session_id}/context/{submission_id}.json"


def _files(session: Session, row: Submission) -> list[SubmissionFile]:
    """The submission's files with their types, in the order they were handed in."""
    found = session.execute(
        select(NoteFile.object_key, NoteFile.mime).where(
            NoteFile.user_id == row.user_id,
            NoteFile.session_id == row.session_id,
            NoteFile.object_key.in_(row.file_keys),
        )
    )
    mimes = {key: mime for key, mime in found}
    return [
        SubmissionFile(object_key=key, mime=mimes[key])  # pyright: ignore[reportArgumentType]
        for key in row.file_keys
        if key in mimes
    ]


@periodic_job(SUBMISSION_RETRY, cron="*/10 * * * *")
def submission_retry_job(payload: dict[str, Any]) -> None:
    with Session(get_engine()) as session:
        counts = retry_pending_ai(session, datetime.now(UTC))
        session.commit()
    _log.info("submissions retried", extra={f"{k}_count": v for k, v in counts.items()})
