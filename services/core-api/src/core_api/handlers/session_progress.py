"""Where processing a confirmed session stands (T4.18, US-02 AC11): `session.progress.v1`,
`session.failed.v1`, and the end of `session.processed.v1`, kept on the `study_session` row.

Events arrive twice and out of order, so the row only moves forward: progress keeps the highest
percent, and `processed` and `failed` are terminal. A late progress or failure never undoes a
`processed`; a `processed` (it wrote the results) does replace a `failed`. Whose session it is
comes from the event's `user_id`, which the consumer has checked against the object keys (F2);
a draft, foreign or missing session is logged and ignored.

Logs hold ids, never more.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from core_api.db.models import StudySession
from core_api.messaging.envelope import Event, SessionFailedEvent, SessionProgressEvent
from core_api.repositories.study_session import StudySessionRepository

_log = logging.getLogger("core_api.handlers.session_progress")
TERMINAL = frozenset({"processed", "failed"})


def _locked(
    session: Session, user_id: uuid.UUID, study_session_id: uuid.UUID
) -> StudySession | None:
    study = StudySessionRepository(session, user_id).lock(study_session_id)
    if study is None or study.status != "confirmed":
        _log.warning(
            "session progress ignored",
            extra={"study_session_id": str(study_session_id), "found": study is not None},
        )
        return None
    return study


def mark_processed(session: Session, user_id: uuid.UUID, study_session_id: uuid.UUID) -> None:
    study = _locked(session, user_id, study_session_id)
    if study is None or study.processing_state == "processed":
        return
    study.processing_state, study.processing_percent = "processed", 100
    study.processing_step = study.processing_reason = None


def mark_failed(
    session: Session, user_id: uuid.UUID, study_session_id: uuid.UUID, reason: str
) -> None:
    study = _locked(session, user_id, study_session_id)
    if study is None or study.processing_state in TERMINAL:
        return
    study.processing_state, study.processing_reason = "failed", reason
    study.processing_step = study.processing_percent = None


def on_session_progress(session: Session, event: Event) -> None:
    assert isinstance(event, SessionProgressEvent)
    payload = event.payload
    study = _locked(session, event.user_id, payload.study_session_id)
    if study is None or study.processing_state in TERMINAL:
        return
    if study.processing_percent is not None and payload.percent <= study.processing_percent:
        return
    study.processing_state, study.processing_step = "processing", payload.step
    study.processing_percent = payload.percent


def on_session_failed(session: Session, event: Event) -> None:
    assert isinstance(event, SessionFailedEvent)
    mark_failed(session, event.user_id, event.payload.study_session_id, event.payload.reason)
