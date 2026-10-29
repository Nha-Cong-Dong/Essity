"""T4.18 (US-02 AC11): core-api keeps where processing a confirmed session stands and serves it
at `GET /v1/sessions/{id}/progress`. Events arrive twice and out of order: progress keeps the
highest percent, `processed` and `failed` are terminal. Database real, storage a double."""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from result_builders import result
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import StudySession, User
from core_api.handlers.session_processed import OnSessionProcessed
from core_api.handlers.session_progress import on_session_failed, on_session_progress
from core_api.messaging.consumer import HANDLERS
from core_api.messaging.envelope import Event, parse_event
from fake_storage import FakeStorage
from sessions.session_helpers import subject_of

RUN = uuid.uuid4()


def study_of(db: Session, user: User, status: str = "confirmed") -> StudySession:
    subject = subject_of(db, user)
    study = StudySession(subject_id=subject.id, description_raw="x", extraction="proposed")
    study.user_id = user.id
    db.add(study)
    db.flush()
    if status == "confirmed":
        study.status = "confirmed"
        study.studied_on = study.learning_day = FROZEN_NOW.date()
        study.confirmed_at = FROZEN_NOW
        db.flush()
    return study


def event(kind: str, user: User, study: StudySession, **payload: Any) -> Event:
    return parse_event(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": f"session.{kind}.v1",
                "schema_version": 1,
                "occurred_at": "2026-10-29T08:01:00.000000Z",
                "user_id": str(user.id),
                "trace_context": {},
                "payload": {"study_session_id": str(study.id), "run_id": str(RUN)} | payload,
            }
        )
    )


def progress(user: User, study: StudySession, percent: int, step: str = "anchoring") -> Event:
    return event("progress", user, study, step=step, percent=percent)


def failed(user: User, study: StudySession, reason: str = "llm_unavailable") -> Event:
    return event("failed", user, study, reason=reason)


def processed(db: Session, user: User, study: StudySession, storage: FakeStorage) -> None:
    key = (
        f"users/{user.id}/subjects/{study.subject_id}/sessions/{study.id}/"
        f"result-{uuid.uuid4()}.json"
    )
    storage.write(key, json.dumps(result(study.id)).encode(), content_type="application/json")
    OnSessionProcessed(storage)(db, event("processed", user, study, result_key=key))


def get(client: TestClient, headers: dict[str, str], study_id: uuid.UUID) -> Any:
    return client.get(f"/v1/sessions/{study_id}/progress", headers=headers)


def state(db: Session, study: StudySession) -> tuple[Any, ...]:
    db.flush()
    db.refresh(study)
    return (
        study.processing_state,
        study.processing_step,
        study.processing_percent,
        study.processing_reason,
    )


def test_progress_is_stored(db_session: Session, two_users: tuple[User, User]) -> None:
    user = two_users[0]
    study = study_of(db_session, user)
    on_session_progress(db_session, progress(user, study, 40, "splitting_units"))
    assert state(db_session, study) == ("processing", "splitting_units", 40, None)


def test_older_or_duplicate_progress_does_not_move_it_back(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    user = two_users[0]
    study = study_of(db_session, user)
    on_session_progress(db_session, progress(user, study, 60, "anchoring"))
    on_session_progress(db_session, progress(user, study, 20, "reading_notes"))
    on_session_progress(db_session, progress(user, study, 60, "reading_notes"))
    assert state(db_session, study) == ("processing", "anchoring", 60, None)


def test_failed_is_terminal_and_progress_after_it_is_ignored(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    user = two_users[0]
    study = study_of(db_session, user)
    on_session_progress(db_session, progress(user, study, 30))
    on_session_failed(db_session, failed(user, study, "unreadable"))
    on_session_progress(db_session, progress(user, study, 90))
    on_session_failed(db_session, failed(user, study, "internal_error"))
    assert state(db_session, study) == ("failed", None, None, "unreadable")


def test_failed_before_any_progress(db_session: Session, two_users: tuple[User, User]) -> None:
    user = two_users[0]
    study = study_of(db_session, user)
    on_session_failed(db_session, failed(user, study))
    assert state(db_session, study)[0] == "failed"


def test_processed_is_terminal_late_progress_and_failure_ignored(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    user = two_users[0]
    study = study_of(db_session, user)
    processed(db_session, user, study, FakeStorage())
    on_session_progress(db_session, progress(user, study, 50))
    on_session_failed(db_session, failed(user, study))
    assert state(db_session, study) == ("processed", None, 100, None)


def test_processed_replaces_a_failure(db_session: Session, two_users: tuple[User, User]) -> None:
    user = two_users[0]
    study = study_of(db_session, user)
    on_session_failed(db_session, failed(user, study))
    processed(db_session, user, study, FakeStorage())
    assert state(db_session, study)[0] == "processed"


def test_result_that_cannot_be_written_ends_as_failed(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    user = two_users[0]
    study = study_of(db_session, user)
    key = (
        f"users/{user.id}/subjects/{study.subject_id}/sessions/{study.id}/"
        f"result-{uuid.uuid4()}.json"
    )
    OnSessionProcessed(FakeStorage())(db_session, event("processed", user, study, result_key=key))
    assert state(db_session, study) == ("failed", None, None, "internal_error")


def test_progress_of_a_draft_or_another_users_session_is_ignored(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    u1, u2 = two_users
    draft = study_of(db_session, u1, "draft")
    on_session_progress(db_session, progress(u1, draft, 10))
    mine = study_of(db_session, u1)
    on_session_progress(db_session, progress(u2, mine, 10))
    assert state(db_session, draft)[0] is None
    assert state(db_session, mine)[0] is None


def test_database_refuses_processing_on_a_draft(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    draft = study_of(db_session, two_users[0], "draft")
    draft.processing_state = "processing"
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_endpoint_waiting_then_each_state(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    study = study_of(db_session, user)
    waiting = get(client, headers, study.id)
    assert waiting.status_code == 200
    assert waiting.headers["cache-control"] == "no-store"
    assert waiting.json() == {
        "session_id": str(study.id),
        "state": "waiting",
        "step": None,
        "percent": None,
        "reason": None,
    }
    on_session_progress(db_session, progress(user, study, 55, "writing_questions"))
    assert get(client, headers, study.id).json() == {
        "session_id": str(study.id),
        "state": "processing",
        "step": "writing_questions",
        "percent": 55,
        "reason": None,
    }
    on_session_failed(db_session, failed(user, study, "unreadable"))
    body = get(client, headers, study.id).json()
    assert (body["state"], body["reason"]) == ("failed", "unreadable")


def test_endpoint_done(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    study = study_of(db_session, user)
    processed(db_session, user, study, FakeStorage())
    body = get(client, headers, study.id).json()
    assert (body["state"], body["percent"]) == ("done", 100)


def test_endpoint_other_user_gets_404(client: TestClient, db_session: Session) -> None:
    owner, _ = signed_in(db_session)
    _, other_headers = signed_in(db_session)
    study = study_of(db_session, owner)
    assert get(client, other_headers, study.id).status_code == 404
    assert get(client, other_headers, uuid.uuid4()).status_code == 404


def test_endpoint_draft_is_404(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    assert get(client, headers, study_of(db_session, user, "draft").id).status_code == 404


def test_endpoint_unverified_is_403(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session, verified=False)
    assert get(client, headers, study_of(db_session, user).id).status_code == 403


def test_endpoint_needs_sign_in(client: TestClient) -> None:
    assert client.get(f"/v1/sessions/{uuid.uuid4()}/progress").status_code in (401, 403)


def test_consumer_routes_progress_and_failed_events() -> None:
    assert HANDLERS["session.progress.v1"] is on_session_progress
    assert HANDLERS["session.failed.v1"] is on_session_failed
