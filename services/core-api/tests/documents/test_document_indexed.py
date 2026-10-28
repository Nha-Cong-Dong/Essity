"""`document.indexed.v1` / `document.failed.v1` handlers and `GET /v1/documents/{id}/toc`
(T4.8, US-01 AC4, US-02 AC2).

The handlers run inside the consumer's claimed transaction (T4.4); here they are called on the
test session, twice where idempotence matters.
"""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW, future_exam
from core_api.db.models import Document, Question, User
from core_api.handlers.document_indexed import on_document_failed, on_document_indexed
from core_api.messaging.consumer import HANDLERS
from core_api.messaging.envelope import (
    DocumentFailed,
    DocumentFailedEvent,
    DocumentIndexed,
    DocumentIndexedEvent,
    TraceContext,
)
from core_api.repositories.subject import SubjectRepository
from fake_storage import FakeStorage

SHA = "cd" * 32
pytestmark = pytest.mark.usefixtures("fake_storage")


def uploaded(session: Session, user: User, status: str = "uploaded") -> Document:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
    session.flush()
    document = Document(
        subject_id=subject.id,
        short_name="Chương 3",
        sha256=SHA,
        size_bytes=100,
        object_key=f"users/{user.id}/subjects/{subject.id}/raw/{SHA}.pdf",
        status=status,
        presigned_at=FROZEN_NOW,
        uploaded_at=None if status in ("pending", "rejected") else FROZEN_NOW,
    )
    document.user_id = user.id
    session.add(document)
    session.flush()
    return document


def derived(document: Document, run: uuid.UUID, name: str) -> str:
    return f"users/{document.user_id}/subjects/{document.subject_id}/derived/{run}/{name}"


def indexed_event(
    document: Document, user_id: uuid.UUID | None = None, payload: dict[str, Any] | None = None
) -> DocumentIndexedEvent:
    payload = dict(payload or {})
    run = payload.pop("run_id", uuid.uuid4())
    fields: dict[str, Any] = {
        "document_id": document.id,
        "run_id": run,
        "page_count": 40,
        "toc_key": derived(document, run, "toc.json"),
        "page_labels_key": derived(document, run, "page_labels.json"),
        "page_text_key": derived(document, run, "page_text.json"),
        "thumbnails_prefix": derived(document, run, "thumbs"),
        "unreadable_pages": [7, 3],
    } | payload
    return DocumentIndexedEvent(
        event_id=uuid.uuid4(),
        event_type="document.indexed.v1",
        schema_version=1,
        occurred_at=FROZEN_NOW,
        user_id=user_id or document.user_id,
        trace_context=TraceContext(),
        payload=DocumentIndexed(**fields),
    )


def failed_event(document: Document, user_id: uuid.UUID | None = None) -> DocumentFailedEvent:
    return DocumentFailedEvent(
        event_id=uuid.uuid4(),
        event_type="document.failed.v1",
        schema_version=1,
        occurred_at=FROZEN_NOW,
        user_id=user_id or document.user_id,
        trace_context=TraceContext(),
        payload=DocumentFailed(
            document_id=document.id, run_id=uuid.uuid4(), reason="unreadable", unreadable_pages=[1]
        ),
    )


def test_the_consumer_handles_both_answers() -> None:
    assert HANDLERS["document.indexed.v1"] is on_document_indexed
    assert HANDLERS["document.failed.v1"] is on_document_failed


def test_indexed_stores_the_derived_files_and_pages(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    event = indexed_event(document)

    on_document_indexed(db_session, event)

    db_session.flush()
    db_session.refresh(document)
    assert document.status == "indexed"
    assert document.page_count == 40
    assert document.unreadable_pages == [3, 7]
    assert document.toc_key == event.payload.toc_key
    assert document.run_id == event.payload.run_id


def test_the_same_event_twice_changes_nothing_more(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    event = indexed_event(document)

    on_document_indexed(db_session, event)
    db_session.flush()
    before = (document.status, document.toc_key, document.unreadable_pages)
    on_document_indexed(db_session, event)
    db_session.flush()

    assert (document.status, document.toc_key, document.unreadable_pages) == before
    assert db_session.scalar(select(func.count()).select_from(Document)) == 1


def test_indexing_creates_no_question_us01_ac4(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    count = select(func.count()).select_from(Question)
    before = db_session.scalar(count)

    on_document_indexed(db_session, indexed_event(document))
    db_session.flush()

    assert db_session.scalar(count) == before


def test_failed_stores_the_reason(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)

    on_document_failed(db_session, failed_event(document))

    db_session.flush()
    db_session.refresh(document)
    assert (document.status, document.failure_reason) == ("failed", "unreadable")
    assert document.page_count is None
    assert document.unreadable_pages == [1]


def test_a_later_answer_replaces_an_earlier_one(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    on_document_failed(db_session, failed_event(document))
    db_session.flush()

    on_document_indexed(db_session, indexed_event(document))
    db_session.flush()

    assert (document.status, document.failure_reason) == ("indexed", None)


def test_another_users_document_is_left_alone_f2(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    document = uploaded(db_session, alice)

    on_document_indexed(db_session, indexed_event(document, user_id=bob.id))
    on_document_failed(db_session, failed_event(document, user_id=bob.id))

    db_session.flush()
    db_session.refresh(document)
    assert document.status == "uploaded"


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_an_unconfirmed_document_ignores_answers(db_session: Session, status: str) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user, status)

    on_document_indexed(db_session, indexed_event(document))

    db_session.flush()
    db_session.refresh(document)
    assert document.status == status


def test_an_unknown_document_is_ignored(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    event = indexed_event(document)
    db_session.delete(document)
    db_session.flush()

    on_document_indexed(db_session, event)  # no error: nothing to update


@pytest.mark.parametrize(
    "bad",
    [
        {"toc_key": "users/{u}/subjects/{s}/derived/{other}/toc.json"},
        {"page_text_key": "users/{u}/subjects/{s}/raw/x.pdf"},
        {"unreadable_pages": [41]},
    ],
)
def test_keys_outside_this_run_or_pages_past_the_end_are_refused(
    db_session: Session, bad: dict[str, Any]
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    fill = {"u": document.user_id, "s": document.subject_id, "other": uuid.uuid4()}
    payload = {k: v.format(**fill) if isinstance(v, str) else v for k, v in bad.items()}

    on_document_indexed(db_session, indexed_event(document, payload=payload))

    db_session.flush()
    db_session.refresh(document)
    assert document.status == "uploaded"


def test_the_database_refuses_an_indexed_row_without_its_files(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    document.status = "indexed"
    with pytest.raises(IntegrityError):
        db_session.flush()


# --- GET /v1/documents/{id}/toc


def index(session: Session, document: Document, storage: FakeStorage, body: bytes) -> None:
    event = indexed_event(document)
    on_document_indexed(session, event)
    session.flush()
    storage.put(event.payload.toc_key, body, None)


def test_toc_is_the_derived_file(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers = signed_in(db_session)
    document = uploaded(db_session, user)
    toc: list[dict[str, Any]] = [{"title": "Chương 1", "first": 1, "last": 9, "children": []}]
    index(db_session, document, fake_storage, json.dumps(toc).encode())

    response = client.get(f"/v1/documents/{document.id}/toc", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"document_id": str(document.id), "toc": toc}


def test_toc_of_a_document_not_indexed_is_409(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    document = uploaded(db_session, user)

    response = client.get(f"/v1/documents/{document.id}/toc", headers=headers)

    assert (response.status_code, response.json()["detail"]) == (409, "not_indexed")


def test_toc_of_another_users_document_is_404(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    owner = signed_in(db_session)[0]
    document = uploaded(db_session, owner)
    index(db_session, document, fake_storage, b"[]")
    _, headers = signed_in(db_session)

    response = client.get(f"/v1/documents/{document.id}/toc", headers=headers)

    assert (response.status_code, response.json()["detail"]) == (404, "document_not_found")


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"not json", id="not-json"),
        pytest.param(b"[" + b"0," * (1 << 20) + b"0]", id="too-large"),
    ],
)
def test_toc_that_is_not_json_or_too_large_is_502(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, body: bytes
) -> None:
    user, headers = signed_in(db_session)
    document = uploaded(db_session, user)
    index(db_session, document, fake_storage, body)

    response = client.get(f"/v1/documents/{document.id}/toc", headers=headers)

    assert (response.status_code, response.json()["detail"]) == (502, "toc_invalid")


def test_toc_with_the_store_down_is_503(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers = signed_in(db_session)
    document = uploaded(db_session, user)
    index(db_session, document, fake_storage, b"[]")
    fake_storage.down = True

    response = client.get(f"/v1/documents/{document.id}/toc", headers=headers)

    assert (response.status_code, response.json()["detail"]) == (503, "storage_unavailable")
