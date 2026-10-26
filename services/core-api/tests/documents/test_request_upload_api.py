"""`POST /v1/subjects/{id}/documents`: a short-lived URL to upload one PDF (T4.5, ADR-0012).

Against a storage double; `test_documents_e2e.py` runs the flow on RustFS.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW, future_exam
from core_api.clients.redis import redis_from_url
from core_api.config import get_settings
from core_api.db.models import Document, Subject, User
from core_api.repositories.subject import SubjectRepository
from core_api.security import rate_limit
from fake_storage import FakeStorage

MB = 1024 * 1024
SHA = "ab" * 32

pytestmark = pytest.mark.usefixtures("fake_storage")


def subject_of(session: Session, user: User) -> Subject:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
    session.flush()
    return subject


def ask(
    client: TestClient,
    headers: dict[str, str],
    subject_id: uuid.UUID,
    **overrides: Any,
) -> tuple[int, dict[str, Any]]:
    body: dict[str, Any] = {"filename": "Chương 3.pdf", "size_bytes": MB, "sha256": SHA}
    body.update(overrides)
    response = client.post(f"/v1/subjects/{subject_id}/documents", json=body, headers=headers)
    return response.status_code, response.json()


def rows(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Document)) or 0


def test_a_new_file_gets_a_put_url_for_its_raw_key(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)

    response = client.post(
        f"/v1/subjects/{subject.id}/documents",
        json={"filename": "Chương 3.pdf", "size_bytes": MB, "sha256": SHA},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    # A signed URL is a credential: never cached on the way back (plan P10).
    assert response.headers["Cache-Control"] == "no-store"
    out = response.json()
    [signed] = fake_storage.presigned
    assert signed.key == f"users/{user.id}/subjects/{subject.id}/raw/{SHA}.pdf"
    assert (signed.size, signed.sha256, signed.content_type) == (MB, SHA, "application/pdf")
    assert out["duplicate"] is False
    assert out["upload"]["method"] == "PUT"
    assert out["upload"]["url"].startswith("https://files.example/bucket/users/")
    assert set(out["upload"]["headers"]) == {
        "Content-Type",
        "x-amz-checksum-sha256",
        "If-None-Match",
    }
    document = out["document"]
    assert document["subject_id"] == str(subject.id)
    assert (document["short_name"], document["status"], document["size_bytes"]) == (
        "Chương 3",
        "pending",
        MB,
    )
    assert "object_key" not in document and "sha256" not in document
    assert db_session.get(Document, uuid.UUID(document["id"])) is not None


def test_the_url_lives_a_few_minutes(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # PLAN T4.5: "URL hết hạn sau vài phút" (plan P4).
    user, headers = signed_in(db_session)
    status, out = ask(client, headers, subject_of(db_session, user).id)
    assert status == 201
    seconds = get_settings().s3_presign_seconds
    assert seconds == 300
    assert fake_storage.presigned[0].expires_in == seconds
    expires_at = datetime.fromisoformat(out["upload"]["expires_at"])
    assert expires_at == FROZEN_NOW + timedelta(seconds=seconds)


def test_b_cannot_get_a_url_for_as_subject(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # PLAN T4.5 "Xong khi": B never gets a URL into A's space (plan P5 a).
    alice, _ = signed_in(db_session)
    _, bobs_headers = signed_in(db_session)
    alices = subject_of(db_session, alice)

    foreign = ask(client, bobs_headers, alices.id)
    unknown = ask(client, bobs_headers, uuid.uuid4())

    assert foreign == unknown == (404, {"detail": "subject_not_found"})
    assert fake_storage.presigned == []
    assert rows(db_session) == 0


def test_the_same_file_of_another_user_is_their_own(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Never deduplicated across users: B learns nothing of A's files (plan P5 b).
    alice, alices_headers = signed_in(db_session)
    bob, bobs_headers = signed_in(db_session)
    assert ask(client, alices_headers, subject_of(db_session, alice).id)[0] == 201

    status, out = ask(client, bobs_headers, subject_of(db_session, bob).id)

    assert (status, out["duplicate"]) == (201, False)
    assert fake_storage.presigned[1].key.startswith(f"users/{bob.id}/")


def test_a_deleted_subject_takes_no_file(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    SubjectRepository(db_session, user.id).soft_delete(subject.id, FROZEN_NOW)
    db_session.flush()
    assert ask(client, headers, subject.id) == (404, {"detail": "subject_not_found"})


def test_pdf_renamed_png_refused(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # PLAN T4.5 "Xong khi": a PDF renamed .png is refused (plan P21).
    user, headers = signed_in(db_session)
    status, out = ask(client, headers, subject_of(db_session, user).id, filename="slides.png")
    assert (status, out) == (422, {"detail": "unsupported_file_type"})
    assert fake_storage.presigned == []
    assert rows(db_session) == 0


def test_a_name_with_nothing_visible_is_refused(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    status, out = ask(client, headers, subject_of(db_session, user).id, filename="‮.pdf")
    assert (status, out) == (422, {"detail": "invalid_filename"})


def test_a_file_over_the_size_limit_is_refused(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers = signed_in(db_session)
    limit = get_settings().document_max_bytes
    subject = subject_of(db_session, user)
    assert ask(client, headers, subject.id, size_bytes=limit + 1) == (
        422,
        {"detail": "file_too_large"},
    )
    assert fake_storage.presigned == []
    assert ask(client, headers, subject.id, size_bytes=limit)[0] == 201


@pytest.mark.parametrize(
    "overrides",
    [
        {"size_bytes": 0},
        {"size_bytes": -1},
        {"size_bytes": "1"},  # a string is not a size
        {"size_bytes": 1.5},
        {"sha256": SHA.upper()},
        {"sha256": SHA[:-1]},
        {"filename": ""},
        {"filename": "a" * 252 + ".pdf"},  # 256 characters
        {"filename": "a\x00.pdf"},
        {"object_key": "users/x/raw/y.pdf"},  # never taken from the client
        {"content_type": "application/pdf"},
    ],
)
def test_malformed_requests_are_refused(
    client: TestClient, db_session: Session, overrides: dict[str, Any]
) -> None:
    user, headers = signed_in(db_session)
    status, _ = ask(client, headers, subject_of(db_session, user).id, **overrides)
    assert status == 422
    assert rows(db_session) == 0


def test_an_uploaded_file_again_is_a_duplicate_without_url(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # US-02 AC13: the same file is not loaded twice; the first name stays.
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    _, first = ask(client, headers, subject.id)
    document = db_session.get_one(Document, uuid.UUID(first["document"]["id"]))
    document.status, document.uploaded_at = "uploaded", FROZEN_NOW
    db_session.flush()

    status, out = ask(client, headers, subject.id, filename="Bản khác.pdf")

    assert (status, out["duplicate"], out["upload"]) == (200, True, None)
    assert out["document"]["id"] == first["document"]["id"]
    assert out["document"]["short_name"] == "Chương 3"
    assert out["document"]["status"] == "uploaded"
    assert len(fake_storage.presigned) == 1
    assert rows(db_session) == 1


def test_a_pending_file_again_gets_a_new_url_for_the_same_row(
    client: TestClient,
    db_session: Session,
    fake_storage: FakeStorage,
    set_now: Callable[[datetime], None],
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    _, first = ask(client, headers, subject.id)
    later = FROZEN_NOW + timedelta(minutes=20)
    set_now(later)

    status, out = ask(client, headers, subject.id)

    assert (status, out["duplicate"]) == (200, False)
    assert out["document"]["id"] == first["document"]["id"]
    assert datetime.fromisoformat(out["upload"]["expires_at"]) == later + timedelta(minutes=5)
    assert len(fake_storage.presigned) == 2
    assert rows(db_session) == 1


def test_a_pending_file_again_with_another_size_is_refused(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    ask(client, headers, subject.id)
    assert ask(client, headers, subject.id, size_bytes=2 * MB) == (
        422,
        {"detail": "size_mismatch"},
    )


def test_a_rejected_file_again_is_refused(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    _, first = ask(client, headers, subject.id)
    db_session.get_one(Document, uuid.UUID(first["document"]["id"])).status = "rejected"
    db_session.flush()
    assert ask(client, headers, subject.id) == (422, {"detail": "content_mismatch"})


def test_the_account_quota_is_a_409(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CORE_DOCUMENT_QUOTA_BYTES", str(3 * MB))
    get_settings.cache_clear()
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    assert ask(client, headers, subject.id, size_bytes=2 * MB)[0] == 201
    assert ask(client, headers, subject.id, sha256="cd" * 32, size_bytes=2 * MB) == (
        409,
        {"detail": "storage_quota_exceeded"},
    )


def test_the_store_cap_is_a_503(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored = db_session.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0))) or 0
    monkeypatch.setenv("CORE_STORAGE_GLOBAL_QUOTA_BYTES", str(stored + MB - 1))
    get_settings.cache_clear()
    user, headers = signed_in(db_session)
    assert ask(client, headers, subject_of(db_session, user).id) == (
        503,
        {"detail": "storage_full"},
    )


def test_asking_too_often_is_a_429(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every ask counts, a new URL for a pending file too (plan D6).
    monkeypatch.setenv("CORE_DOCUMENT_UPLOADS_PER_HOUR", "2")
    get_settings.cache_clear()
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    assert ask(client, headers, subject.id)[0] == 201
    assert ask(client, headers, subject.id)[0] == 200
    response = client.post(
        f"/v1/subjects/{subject.id}/documents",
        json={"filename": "a.pdf", "size_bytes": MB, "sha256": "cd" * 32},
        headers=headers,
    )
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_the_limit_is_per_account(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CORE_DOCUMENT_UPLOADS_PER_HOUR", "1")
    get_settings.cache_clear()
    for _ in range(2):
        user, headers = signed_in(db_session)
        assert ask(client, headers, subject_of(db_session, user).id)[0] == 201


def test_redis_down_is_a_503(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    dead = redis_from_url("redis://127.0.0.1:1/0", timeout=0.2)
    monkeypatch.setattr(rate_limit, "get_redis", lambda: dead)
    assert ask(client, headers, subject.id)[0] == 503
    assert rows(db_session) == 0


def test_no_file_name_key_or_url_in_the_logs(
    client: TestClient, db_session: Session, log_output: Callable[[], str]
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    _, out = ask(client, headers, subject.id, filename="Bí mật riêng.pdf")
    logged = log_output()
    assert "Bí mật" not in logged and "B\\u00ed m\\u1eadt" not in logged
    assert SHA not in logged
    assert "X-Amz-Signature" not in logged
    assert out["upload"]["url"] not in logged
