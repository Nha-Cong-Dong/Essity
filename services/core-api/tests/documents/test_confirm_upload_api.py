"""`POST /v1/documents/{id}/confirm`: check what arrived, then announce it (T4.5, ADR-0012).

Size, stored SHA-256 and PDF header are checked before `document.uploaded.v1` goes to the
outbox, in the transaction that marks the document uploaded. A refused file is deleted and its
row kept as `rejected` until cleanup (plan R1).

Against a storage double; `test_documents_e2e.py` runs the flow on RustFS.
"""

import base64
import hashlib
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
from fake_storage import FakeStorage

PDF = b"%PDF-1.7\n" + b"x" * 100
PDF_SHA = hashlib.sha256(PDF).hexdigest()
# base64 of SHA-256(PDF), as a store sends it: written out, not computed by the code (plan P12).
PDF_SHA_B64 = "dcDLsbHDXF6qpwyQZaowiQP42JPB37gwUxpRS1GrToU="
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 101  # as long as PDF

pytestmark = pytest.mark.usefixtures("fake_storage")


def test_the_written_checksum_is_the_pdfs() -> None:
    assert base64.b64decode(PDF_SHA_B64).hex() == PDF_SHA


def subject_of(session: Session, user: User) -> Subject:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
    session.flush()
    return subject


def asked(
    client: TestClient, session: Session, *, sha256: str = PDF_SHA, size: int = len(PDF)
) -> tuple[User, dict[str, str], Document]:
    """A signed-in user with a document waiting for its file."""
    user, headers = signed_in(session)
    subject = subject_of(session, user)
    response = client.post(
        f"/v1/subjects/{subject.id}/documents",
        json={"filename": "Chương 3.pdf", "size_bytes": size, "sha256": sha256},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return user, headers, session.get_one(Document, uuid.UUID(response.json()["document"]["id"]))


def confirm(
    client: TestClient, headers: dict[str, str], document_id: uuid.UUID
) -> tuple[int, dict[str, Any]]:
    response = client.post(f"/v1/documents/{document_id}/confirm", headers=headers)
    return response.status_code, response.json()


def events(session: Session, user: User) -> list[Outbox]:
    return list(session.scalars(select(Outbox).where(Outbox.user_id == user.id)))


def state(session: Session, document: Document) -> str:
    return session.execute(select(Document.status).where(Document.id == document.id)).scalar_one()


def test_a_stored_pdf_is_uploaded_and_announced_once(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PDF, PDF_SHA_B64)

    status, out = confirm(client, headers, document.id)

    assert status == 200, out
    assert (out["id"], out["status"]) == (str(document.id), "uploaded")
    db_session.refresh(document)
    assert document.uploaded_at == FROZEN_NOW
    [event] = events(db_session, user)
    assert event.event_type == "document.uploaded.v1"
    assert event.payload == {
        "document_id": str(document.id),
        "subject_id": str(document.subject_id),
        "object_key": document.object_key,
    }


def test_confirming_twice_announces_once(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PDF, PDF_SHA_B64)
    assert confirm(client, headers, document.id)[0] == 200
    fake_storage.down = True  # nothing to check again: no call to the store

    status, out = confirm(client, headers, document.id)

    assert (status, out["status"]) == (200, "uploaded")
    assert len(events(db_session, user)) == 1


def test_a_store_without_checksums_still_gets_size_and_header_checked(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Fail-open on the SHA-256 only: ai-service recomputes it (T4.7, plan P11).
    _, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PDF, None)
    assert confirm(client, headers, document.id)[0] == 200


def test_confirm_before_the_file_arrived_is_a_409_and_can_be_retried(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Also what an expired URL leads to: ask for a new one, upload, confirm again.
    user, headers, document = asked(client, db_session)

    assert confirm(client, headers, document.id) == (409, {"detail": "upload_incomplete"})
    assert state(db_session, document) == "pending"
    assert events(db_session, user) == []

    fake_storage.put(document.object_key, PDF, PDF_SHA_B64)
    assert confirm(client, headers, document.id)[0] == 200


def test_b_cannot_confirm_as_document(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Plan P5 c: 404 like an unknown id, and nothing of A's moves.
    alice, _, document = asked(client, db_session)
    fake_storage.put(document.object_key, PNG, None)  # would be refused and deleted
    _, bobs_headers = signed_in(db_session)

    foreign = confirm(client, bobs_headers, document.id)
    unknown = confirm(client, bobs_headers, uuid.uuid4())

    assert foreign == unknown == (404, {"detail": "document_not_found"})
    assert fake_storage.deleted == []
    assert state(db_session, document) == "pending"
    assert events(db_session, alice) == []


def test_png_renamed_pdf_refused_at_confirm(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # PLAN T4.5: the bytes decide, not the name (plan P21). The row stays, rejected (R1).
    user, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PNG, None)

    assert confirm(client, headers, document.id) == (422, {"detail": "content_mismatch"})
    assert state(db_session, document) == "rejected"
    assert fake_storage.deleted == [document.object_key]
    assert events(db_session, user) == []


def test_a_file_of_another_size_is_refused(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # A store that does not enforce the signed Content-Length.
    user, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PDF + b"more", None)

    assert confirm(client, headers, document.id) == (422, {"detail": "size_mismatch"})
    assert state(db_session, document) == "rejected"
    assert fake_storage.deleted == [document.object_key]
    assert events(db_session, user) == []


def test_a_file_with_another_checksum_is_refused(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Declared one SHA-256, the store holds another: not the file the key names.
    user, headers, document = asked(client, db_session, sha256="ab" * 32)
    fake_storage.put(document.object_key, PDF, PDF_SHA_B64)

    assert confirm(client, headers, document.id) == (422, {"detail": "content_mismatch"})
    assert state(db_session, document) == "rejected"
    assert events(db_session, user) == []


def test_a_stored_checksum_that_is_not_one_is_refused(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    _, headers, document = asked(client, db_session)
    fake_storage.objects[document.object_key] = (PDF, None)
    fake_storage.checksums_hex[document.object_key] = ""  # what head() gives for junk

    assert confirm(client, headers, document.id) == (422, {"detail": "content_mismatch"})


def test_a_refused_file_confirmed_again_is_refused_without_the_store(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Plan P25: not a 409 that would send web back to upload the same bytes.
    _, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PNG, None)
    confirm(client, headers, document.id)
    fake_storage.down = True

    assert confirm(client, headers, document.id) == (422, {"detail": "content_mismatch"})


def test_store_down_is_a_503_and_the_row_waits(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PDF, PDF_SHA_B64)
    fake_storage.down = True

    assert confirm(client, headers, document.id) == (503, {"detail": "storage_unavailable"})
    assert state(db_session, document) == "pending"
    assert events(db_session, user) == []


def test_a_refusal_that_cannot_delete_the_file_leaves_it_to_cleanup(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # The row stays pending: cleanup deletes object and row once the URL is long dead.
    _, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PNG, None)
    fake_storage.delete_fails = True

    assert confirm(client, headers, document.id) == (503, {"detail": "storage_unavailable"})
    assert state(db_session, document) == "pending"


def test_a_file_for_a_deleted_subject_is_not_announced(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PDF, PDF_SHA_B64)
    SubjectRepository(db_session, user.id).soft_delete(document.subject_id, FROZEN_NOW)
    db_session.flush()

    assert confirm(client, headers, document.id) == (404, {"detail": "subject_not_found"})
    assert events(db_session, user) == []


def test_a_file_already_there_when_the_put_got_412_is_confirmed(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Plan P24: the browser got 412 (the object exists): confirm still checks everything.
    user, headers, document = asked(client, db_session)
    fake_storage.put(document.object_key, PDF, PDF_SHA_B64)
    again = client.post(
        f"/v1/subjects/{document.subject_id}/documents",
        json={"filename": "Chương 3.pdf", "size_bytes": len(PDF), "sha256": PDF_SHA},
        headers=headers,
    )
    assert again.status_code == 200

    assert confirm(client, headers, document.id)[0] == 200
    assert confirm(client, headers, document.id)[0] == 200
    assert len(events(db_session, user)) == 1


@pytest.mark.parametrize("path", ["/v1/documents/not-a-uuid/confirm"])
def test_a_malformed_id_is_a_422(client: TestClient, db_session: Session, path: str) -> None:
    _, headers = signed_in(db_session)
    assert client.post(path, headers=headers).status_code == 422
