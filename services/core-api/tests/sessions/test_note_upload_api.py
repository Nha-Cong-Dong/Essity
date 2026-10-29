"""`POST /v1/sessions/{id}/notes/upload-url`: a short-lived URL to upload one note file of a
draft session (T4.13b, US-02 AC13, ADR-0012). Against a storage double."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from session_helpers import subject_of
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.config import get_settings
from core_api.db.models import NoteUpload, StudySession, User
from fake_storage import FakeStorage

MB = 1024 * 1024
SHA = "ab" * 32

pytestmark = pytest.mark.usefixtures("fake_storage")


def draft_of(db: Session, user: User, status: str = "draft") -> StudySession:
    subject = subject_of(db, user)
    draft = StudySession(subject_id=subject.id, description_raw="x", extraction="failed")
    draft.user_id = user.id
    db.add(draft)
    db.flush()
    if status == "confirmed":
        draft.status = "confirmed"
        draft.studied_on = draft.learning_day = FROZEN_NOW.date()
        draft.confirmed_at = FROZEN_NOW
    return draft


def ask(
    client: TestClient, headers: dict[str, str], session_id: uuid.UUID, **over: Any
) -> tuple[int, dict[str, Any]]:
    body: dict[str, Any] = {"sha256": SHA, "mime": "image/jpeg", "size_bytes": MB} | over
    response = client.post(
        f"/v1/sessions/{session_id}/notes/upload-url", json=body, headers=headers
    )
    return response.status_code, response.json()


def rows(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(NoteUpload)) or 0


def test_new_note_gets_a_put_url_for_its_notes_key(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)

    status, out = ask(client, headers, draft.id)

    assert status == 201
    [signed] = fake_storage.presigned
    assert signed.key == f"users/{user.id}/sessions/{draft.id}/notes/{SHA}.jpg"
    assert (signed.size, signed.sha256, signed.content_type) == (MB, SHA, "image/jpeg")
    assert out["method"] == "PUT"
    assert out["url"].startswith("https://files.example/bucket/users/")
    assert set(out["headers"]) == {"Content-Type", "x-amz-checksum-sha256", "If-None-Match"}
    assert rows(db_session) == 1


def test_response_is_never_cached(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)
    response = client.post(
        f"/v1/sessions/{draft.id}/notes/upload-url",
        json={"sha256": SHA, "mime": "image/png", "size_bytes": 5},
        headers=headers,
    )
    assert response.headers["Cache-Control"] == "no-store"


def test_same_file_again_is_one_row_and_a_fresh_url(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)
    assert ask(client, headers, draft.id)[0] == 201
    assert ask(client, headers, draft.id)[0] == 200
    assert rows(db_session) == 1
    assert len(fake_storage.presigned) == 2


def test_same_hash_with_another_size_or_type_is_refused(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)
    assert ask(client, headers, draft.id)[0] == 201
    assert ask(client, headers, draft.id, size_bytes=MB + 1) == (422, {"detail": "bad_note"})
    assert ask(client, headers, draft.id, mime="image/png") == (422, {"detail": "bad_note"})


@pytest.mark.parametrize(
    "mime", ["image/gif", "image/svg+xml", "text/html", "application/zip", "image/jpeg; x=1"]
)
def test_only_the_allowlisted_types(client: TestClient, db_session: Session, mime: str) -> None:
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)
    assert ask(client, headers, draft.id, mime=mime)[0] == 422
    assert rows(db_session) == 0


def test_size_bounds(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)
    limit = get_settings().note_max_bytes
    assert ask(client, headers, draft.id, size_bytes=limit + 1) == (
        422,
        {"detail": "file_too_large"},
    )
    assert ask(client, headers, draft.id, size_bytes=0)[0] == 422
    assert ask(client, headers, draft.id, size_bytes=limit)[0] == 201


@pytest.mark.parametrize("sha", ["AB" * 32, "ab" * 31, "zz" * 32, ""])
def test_sha256_must_be_lowercase_hex(client: TestClient, db_session: Session, sha: str) -> None:
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)
    assert ask(client, headers, draft.id, sha256=sha)[0] == 422


def test_another_users_session_is_a_404_and_writes_nothing(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    alice, _ = signed_in(db_session)
    _, bob_headers = signed_in(db_session)
    draft = draft_of(db_session, alice)

    assert ask(client, bob_headers, draft.id) == (404, {"detail": "session_not_found"})
    assert ask(client, bob_headers, uuid.uuid4()) == (404, {"detail": "session_not_found"})
    assert rows(db_session) == 0
    assert fake_storage.presigned == []


def test_unverified_gets_no_url(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session, verified=False)
    draft = draft_of(db_session, user)
    assert ask(client, headers, draft.id)[0] == 403
    assert rows(db_session) == 0


def test_no_token_is_401(client: TestClient, db_session: Session) -> None:
    user, _ = signed_in(db_session)
    draft = draft_of(db_session, user)
    assert ask(client, {}, draft.id)[0] == 401


def test_confirmed_session_takes_no_more_notes(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user, "confirmed")
    assert ask(client, headers, draft.id) == (409, {"detail": "session_confirmed"})


def test_at_most_20_notes_per_session(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)
    for i in range(20):
        assert ask(client, headers, draft.id, sha256=f"{i:064x}", size_bytes=1)[0] == 201
    assert ask(client, headers, draft.id, sha256="f" * 64, size_bytes=1) == (
        409,
        {"detail": "too_many_notes"},
    )
    # A fresh URL for one of the 20 is not a 21st.
    assert ask(client, headers, draft.id, sha256=f"{3:064x}", size_bytes=1)[0] == 200


def test_quota_counts_notes_on_their_way(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CORE_NOTE_QUOTA_BYTES", str(3 * MB))
    get_settings.cache_clear()
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)
    assert ask(client, headers, draft.id, sha256="01" * 32, size_bytes=2 * MB)[0] == 201
    assert ask(client, headers, draft.id, sha256="02" * 32, size_bytes=MB + 1) == (
        409,
        {"detail": "storage_quota_exceeded"},
    )
    assert ask(client, headers, draft.id, sha256="02" * 32, size_bytes=MB)[0] == 201
    assert rows(db_session) == 2


def test_quota_is_per_account(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CORE_NOTE_QUOTA_BYTES", str(MB))
    get_settings.cache_clear()
    for _ in range(2):
        user, headers = signed_in(db_session)
        assert ask(client, headers, draft_of(db_session, user).id)[0] == 201


def test_asking_too_often_is_a_429(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CORE_NOTE_UPLOADS_PER_HOUR", "2")
    get_settings.cache_clear()
    user, headers = signed_in(db_session)
    draft = draft_of(db_session, user)
    assert ask(client, headers, draft.id)[0] == 201
    assert ask(client, headers, draft.id)[0] == 200
    response = client.post(
        f"/v1/sessions/{draft.id}/notes/upload-url",
        json={"sha256": "cd" * 32, "mime": "image/png", "size_bytes": 5},
        headers=headers,
    )
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
