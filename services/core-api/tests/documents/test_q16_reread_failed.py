"""Q16 (QA 05/11): asking to upload the same file again while its earlier reading failed reads it
again (status back to uploaded, one new `document.uploaded` event) instead of returning the failed
document untouched. Another user's failed document of the same hash is not touched."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW, future_exam
from core_api.db.models import Document, Outbox, Subject, User
from core_api.repositories.subject import SubjectRepository

MB = 1024 * 1024
SHA = "cd" * 32

pytestmark = pytest.mark.usefixtures("fake_storage")


def _subject(session: Session, user: User) -> Subject:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
    session.flush()
    return subject


def _failed(session: Session, user: User, subject: Subject) -> Document:
    document = Document(
        subject_id=subject.id,
        short_name="hong",
        sha256=SHA,
        size_bytes=MB,
        object_key=f"users/{user.id}/subjects/{subject.id}/raw/{SHA}.pdf",
        status="failed",
        failure_reason="unreadable",
        presigned_at=FROZEN_NOW,
        uploaded_at=FROZEN_NOW,
    )
    document.user_id = user.id
    session.add(document)
    session.commit()
    return document


def _ask(client: TestClient, headers: dict[str, str], subject: Subject) -> Any:
    return client.post(
        f"/v1/subjects/{subject.id}/documents",
        json={"filename": "hong.pdf", "size_bytes": MB, "sha256": SHA},
        headers=headers,
    )


def _events(session: Session, user: User) -> list[Outbox]:
    return list(session.scalars(select(Outbox).where(Outbox.user_id == user.id)))


def test_the_same_failed_file_is_read_again(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    subject = _subject(db_session, user)
    document = _failed(db_session, user, subject)

    response = _ask(client, headers, subject)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duplicate"] is True and body["upload"] is None
    assert (body["document"]["id"], body["document"]["status"]) == (str(document.id), "uploaded")
    db_session.expire_all()
    fresh = db_session.get_one(Document, document.id)
    assert (fresh.status, fresh.failure_reason) == ("uploaded", None)
    [event] = _events(db_session, user)
    assert event.event_type == "document.uploaded.v1"
    assert event.payload["document_id"] == str(document.id)


def test_asking_again_while_it_is_being_read_does_not_enqueue_twice(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = _subject(db_session, user)
    _failed(db_session, user, subject)
    assert _ask(client, headers, subject).status_code == 200
    assert _ask(client, headers, subject).status_code == 200
    assert len(_events(db_session, user)) == 1


def test_another_users_failed_document_of_the_same_hash_is_untouched(
    client: TestClient, db_session: Session
) -> None:
    alice, alice_headers = signed_in(db_session)
    bob, _ = signed_in(db_session)
    mine = _subject(db_session, alice)
    theirs = _subject(db_session, bob)
    _failed(db_session, alice, mine)
    bobs = _failed(db_session, bob, theirs)

    assert _ask(client, alice_headers, mine).status_code == 200

    db_session.expire_all()
    assert db_session.get_one(Document, bobs.id).status == "failed"
    assert _events(db_session, bob) == []
    assert uuid.UUID(str(bobs.id))
