"""POST /v1/submissions from two real connections (T7.6; US-02 AC10 one submission per session,
plan "Đồng thời": the draft row is locked FOR UPDATE as in confirm). The setup commits; the
teardown deletes the user, which takes the rows with it. Tester round 2."""

import hashlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import Response
from session_helpers import subject_of
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from clock import FROZEN_NOW
from core_api.api.submissions import FileIn, SubmitRequest, submit
from core_api.db.models import Outbox, StudySession, Submission, User
from core_api.repositories.user import UserRepository
from fake_storage import FakeStorage
from races import finished, in_thread, wait_for_lock


@dataclass
class Ready:
    user_id: uuid.UUID
    draft_id: uuid.UUID


class NoLimit:
    def enforce(self, *_: Any) -> None:
        return None


@pytest.fixture
def ready(engine: Engine) -> Iterator[Ready]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t76-race-{uuid.uuid4().hex[:12]}@example.com")
        session.flush()
        user.email_verified_at = datetime.now(UTC)
        subject = subject_of(session, user)
        draft = StudySession(
            subject_id=subject.id, description_raw="(bài nộp)", extraction="failed"
        )
        draft.user_id = user.id
        session.add(draft)
        session.flush()
        made = Ready(user.id, draft.id)
        session.commit()
    yield made
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM outbox WHERE user_id = :id"), {"id": made.user_id})
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": made.user_id})


def _pdf(storage: FakeStorage, ready: Ready, body: bytes) -> FileIn:
    data = b"%PDF-1.7 " + body
    digest = hashlib.sha256(data).hexdigest()
    key = f"users/{ready.user_id}/sessions/{ready.draft_id}/notes/{digest}.pdf"
    storage.put(key, data, None)
    return FileIn(sha256=digest, mime="application/pdf", size_bytes=len(data))


def _submit(session: Session, storage: FakeStorage, ready: Ready, file: FileIn) -> Response:
    user = session.get(User, ready.user_id)
    assert user is not None
    response = Response()
    response.status_code = 201
    submit(
        SubmitRequest(session_id=ready.draft_id, files=[file]),
        user,  # pyright: ignore[reportArgumentType]
        session,
        storage,  # pyright: ignore[reportArgumentType]
        NoLimit(),  # pyright: ignore[reportArgumentType]
        FROZEN_NOW,
        response,
    )
    return response


def test_two_submits_of_one_session_at_once_make_one_submission(
    engine: Engine, ready: Ready
) -> None:
    # Red when: the draft row is read without FOR UPDATE, so a second submit made while the
    # first is still open sees no submission yet and queues a second one (two events, the AI
    # pays twice, two sets of drafts). With the lock it waits, then answers 200 with the first.
    storage = FakeStorage()
    first, second = _pdf(storage, ready, b"one"), _pdf(storage, ready, b"two")
    with Session(engine) as a, Session(engine) as b:
        assert _submit(a, storage, ready, first).status_code == 201
        pid = b.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(lambda: _submit(b, storage, ready, second))
        wait_for_lock(engine, pid, outcome)
        a.commit()
        result = finished(thread, outcome)
        assert isinstance(result, Response), result
        assert result.status_code == 200
        b.commit()
    with Session(engine) as check:
        count = select(func.count()).select_from(Submission)
        assert check.scalar(count.where(Submission.session_id == ready.draft_id)) == 1
        events = select(func.count()).select_from(Outbox)
        assert (
            check.scalar(
                events.where(
                    Outbox.user_id == ready.user_id, Outbox.event_type == "submission.created.v1"
                )
            )
            == 1
        )
