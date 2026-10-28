"""Upload end to end on the real store (RustFS), through the app's own database sessions (T4.5).

What the double cannot show: the URL the app signs really works for the declared PDF and only
for it, the checksum the store keeps matches, a refused file is really gone, and a failure after
`enqueue_event` leaves neither the upload nor the event (one transaction, plan P12, P24).
Data is committed here, and removed with its user afterwards.
"""

import hashlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import future_exam
from core_api.api import documents as documents_api
from core_api.api.deps import get_storage
from core_api.clients.storage import S3Storage
from core_api.config import get_settings
from core_api.db.models import Document, Outbox
from core_api.main import app
from core_api.repositories.subject import SubjectRepository
from core_api.security.client_ip import CLIENT_IP_HEADER
from core_api.security.service_token import SERVICE_TOKEN_HEADER
from object_store import storage_on

PDF = b"%PDF-1.7\n" + b"e2e " * 64 + b"\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"e2e " * 64
WEB_TOKEN = "e2e-web-token-0123456789abcdefghijkl"


@dataclass
class Account:
    user_id: uuid.UUID
    headers: dict[str, str]
    subject_id: uuid.UUID


def account(engine: Engine) -> Account:
    with Session(engine) as session:
        user, headers = signed_in(session)
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
        made = Account(user.id, headers, subject.id)
        session.commit()
    return made


@pytest.fixture
def accounts(engine: Engine) -> Iterator[list[Account]]:
    made = [account(engine), account(engine)]
    yield made
    with engine.begin() as connection:
        for one in made:
            # The outbox keeps no foreign key to the user (it must outlive them): by hand.
            connection.execute(text("DELETE FROM outbox WHERE user_id = :u"), {"u": one.user_id})
            connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": one.user_id})


@pytest.fixture
def storage(s3_bucket: str) -> Iterator[S3Storage]:
    real = storage_on(s3_bucket)
    app.dependency_overrides[get_storage] = lambda: real
    yield real
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def app_client(monkeypatch: pytest.MonkeyPatch, storage: S3Storage) -> TestClient:
    """The app with its own sessions: each request commits or rolls back for real."""
    monkeypatch.setenv("CORE_WEB_TOKEN", WEB_TOKEN)
    get_settings.cache_clear()
    headers = {SERVICE_TOKEN_HEADER: WEB_TOKEN, CLIENT_IP_HEADER: "10.45.0.1"}
    return TestClient(app, headers=headers, raise_server_exceptions=False)


def ask(client: TestClient, who: Account, body: bytes) -> dict[str, Any]:
    response = client.post(
        f"/v1/subjects/{who.subject_id}/documents",
        json={
            "filename": "Chương 3.pdf",
            "size_bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        },
        headers=who.headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def put(asked: dict[str, Any], body: bytes) -> int:
    upload = asked["upload"]
    return httpx2.put(upload["url"], content=body, headers=upload["headers"]).status_code


def confirm(client: TestClient, who: Account, document_id: str) -> tuple[int, Any]:
    response = client.post(f"/v1/documents/{document_id}/confirm", headers=who.headers)
    return response.status_code, response.json()


def document_row(engine: Engine, document_id: str) -> Document | None:
    with Session(engine) as session:
        return session.get(Document, uuid.UUID(document_id))


def events_of(engine: Engine, who: Account) -> list[Outbox]:
    with Session(engine) as session:
        return list(session.scalars(select(Outbox).where(Outbox.user_id == who.user_id)))


def key_of(who: Account, body: bytes) -> str:
    sha = hashlib.sha256(body).hexdigest()
    return f"users/{who.user_id}/subjects/{who.subject_id}/raw/{sha}.pdf"


def test_a_pdf_goes_up_and_is_announced(
    app_client: TestClient, engine: Engine, storage: S3Storage, accounts: list[Account]
) -> None:
    alice = accounts[0]
    asked = ask(app_client, alice, PDF)
    # A few minutes, in the URL the store will check (PLAN T4.5).
    url: str = asked["upload"]["url"]
    expires = parse_qs(urlsplit(url).query)["X-Amz-Expires"]
    assert expires == [str(get_settings().s3_presign_seconds)]

    assert put(asked, PDF) == 200
    status, out = confirm(app_client, alice, asked["document"]["id"])

    assert (status, out["status"]) == (200, "uploaded")
    stored = storage.head(key_of(alice, PDF))
    assert stored is not None and stored.sha256 == hashlib.sha256(PDF).hexdigest()
    [event] = events_of(engine, alice)
    assert event.payload["object_key"] == key_of(alice, PDF)


def test_another_file_on_the_url_is_refused_by_the_store(
    app_client: TestClient, storage: S3Storage, accounts: list[Account]
) -> None:
    alice = accounts[0]
    asked = ask(app_client, alice, PDF)
    other = PDF.replace(b"e2e", b"zzz")
    assert put(asked, other) == 400  # BadDigest: the signed SHA-256
    assert storage.head(key_of(alice, PDF)) is None


def test_png_renamed_pdf_is_refused_and_deleted(
    app_client: TestClient, engine: Engine, storage: S3Storage, accounts: list[Account]
) -> None:
    alice = accounts[0]
    asked = ask(app_client, alice, PNG)
    assert put(asked, PNG) == 200

    assert confirm(app_client, alice, asked["document"]["id"]) == (
        422,
        {"detail": "content_mismatch"},
    )
    assert storage.head(key_of(alice, PNG)) is None
    row = document_row(engine, asked["document"]["id"])
    assert row is not None and row.status == "rejected"  # committed, not rolled back
    assert events_of(engine, alice) == []


def test_b_cannot_confirm_as_upload(
    app_client: TestClient, engine: Engine, storage: S3Storage, accounts: list[Account]
) -> None:
    alice, bob = accounts
    asked = ask(app_client, alice, PDF)
    assert put(asked, PDF) == 200

    assert confirm(app_client, bob, asked["document"]["id"]) == (
        404,
        {"detail": "document_not_found"},
    )
    assert storage.head(key_of(alice, PDF)) is not None
    row = document_row(engine, asked["document"]["id"])
    assert row is not None and row.status == "pending"
    assert events_of(engine, alice) == events_of(engine, bob) == []


def test_after_a_412_confirm_still_works_once(
    app_client: TestClient, engine: Engine, accounts: list[Account]
) -> None:
    # The first PUT landed but its answer was lost; the retry gets a new URL and a 412.
    alice = accounts[0]
    first = ask(app_client, alice, PDF)
    assert put(first, PDF) == 200
    second = ask(app_client, alice, PDF)
    assert second["document"]["id"] == first["document"]["id"]
    assert put(second, PDF) == 412

    assert confirm(app_client, alice, first["document"]["id"])[0] == 200
    assert confirm(app_client, alice, first["document"]["id"])[0] == 200
    assert len(events_of(engine, alice)) == 1


def test_a_failure_after_the_event_leaves_neither(
    app_client: TestClient,
    engine: Engine,
    accounts: list[Account],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: the event is written outside the request's transaction, or the status is.
    alice = accounts[0]
    asked = ask(app_client, alice, PDF)
    assert put(asked, PDF) == 200
    real_enqueue = documents_api.enqueue_event

    def enqueue_then_fail(*args: Any, **kwargs: Any) -> uuid.UUID:
        real_enqueue(*args, **kwargs)
        raise RuntimeError("crash after the event")

    monkeypatch.setattr(documents_api, "enqueue_event", enqueue_then_fail)

    path = f"/v1/documents/{asked['document']['id']}/confirm"
    assert app_client.post(path, headers=alice.headers).status_code == 500

    row = document_row(engine, asked["document"]["id"])
    assert row is not None and row.status == "pending"
    assert events_of(engine, alice) == []
    monkeypatch.undo()
    assert confirm(app_client, alice, asked["document"]["id"])[0] == 200
