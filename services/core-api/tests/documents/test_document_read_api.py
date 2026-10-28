"""`GET /v1/subjects/{id}/documents` and `GET /v1/documents/{id}` (T4.9 API).

A user reads only their own documents; another user's subject or document is a 404, the same as
one that does not exist.
"""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW, future_exam
from core_api.db.models import Document, Subject, User
from core_api.repositories.subject import SubjectRepository

pytestmark = pytest.mark.usefixtures("fake_storage")


def subject_of(session: Session, user: User) -> Subject:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
    session.flush()
    return subject


def document_in(
    session: Session, user: User, subject: Subject, name: str, age: int = 0
) -> Document:
    sha = uuid.uuid4().hex + uuid.uuid4().hex
    document = Document(
        subject_id=subject.id,
        short_name=name,
        sha256=sha,
        size_bytes=100,
        object_key=f"users/{user.id}/subjects/{subject.id}/raw/{sha}.pdf",
        status="uploaded",
        presigned_at=FROZEN_NOW,
        uploaded_at=FROZEN_NOW,
    )
    document.user_id = user.id
    document.created_at = FROZEN_NOW - timedelta(minutes=age)
    session.add(document)
    session.flush()
    return document


def test_lists_the_subjects_documents_oldest_first(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    newer = document_in(db_session, user, subject, "Chương 4", age=1)
    older = document_in(db_session, user, subject, "Chương 3", age=5)
    document_in(db_session, user, subject_of(db_session, user), "Môn khác")

    response = client.get(f"/v1/subjects/{subject.id}/documents", headers=headers)

    assert response.status_code == 200
    assert [d["id"] for d in response.json()] == [str(older.id), str(newer.id)]
    assert response.json()[0]["short_name"] == "Chương 3"
    assert response.json()[0]["status"] == "uploaded"


def test_an_empty_subject_lists_nothing(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    response = client.get(f"/v1/subjects/{subject.id}/documents", headers=headers)
    assert (response.status_code, response.json()) == (200, [])


def test_another_users_subject_is_not_found(client: TestClient, db_session: Session) -> None:
    owner, _ = signed_in(db_session)
    subject = subject_of(db_session, owner)
    document_in(db_session, owner, subject, "Chương 3")
    _, headers = signed_in(db_session)

    for path in (str(subject.id), str(uuid.uuid4())):
        response = client.get(f"/v1/subjects/{path}/documents", headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "subject_not_found"


def test_reads_one_document(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    document = document_in(db_session, user, subject_of(db_session, user), "Chương 3")
    response = client.get(f"/v1/documents/{document.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(document.id)
    assert response.headers["cache-control"] == "no-store"


def test_another_users_document_is_not_found(client: TestClient, db_session: Session) -> None:
    owner, _ = signed_in(db_session)
    document = document_in(db_session, owner, subject_of(db_session, owner), "Chương 3")
    _, headers = signed_in(db_session)
    response = client.get(f"/v1/documents/{document.id}", headers=headers)
    assert (response.status_code, response.json()["detail"]) == (404, "document_not_found")


def test_an_unverified_user_reads_nothing(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session, verified=False)
    subject = subject_of(db_session, user)
    document = document_in(db_session, user, subject, "Chương 3")
    assert client.get(f"/v1/subjects/{subject.id}/documents", headers=headers).status_code == 403
    assert client.get(f"/v1/documents/{document.id}", headers=headers).status_code == 403
