"""POST /v1/submissions, edge cases the tester added (T7.6; US-02 AC2 files stored first, AC3
scope context, AC4 clear errors, P4 input ceilings): each one fails under a mutation of
`api/submissions.py` that the first suite let through."""

import hashlib
import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_submissions import World, nothing_written, sha, submit

from core_api.clients.storage import StorageUnavailableError
from core_api.config import get_settings
from core_api.db.models import NoteFile, NoteUpload, Outbox, Submission, UnitSection
from core_api.jobs.note_cleanup import delete_abandoned_notes
from fake_storage import FakeStorage
from v2_rows import make_unit

pytestmark = pytest.mark.usefixtures("fake_storage", "enabled")


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CORE_SUBMISSIONS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.fixture
def world(db_session: Session, fake_storage: FakeStorage) -> World:
    return World(db_session, fake_storage)


def events(world: World) -> list[Outbox]:
    return world.events()


# --- Ceilings and stored-file checks (AC2, P4) ------------------------------------------------


def test_twenty_files_and_typed_text_is_422_not_a_database_error(
    client: TestClient, world: World
) -> None:
    # Red when: the 21st file (the typed text) is not counted against FILE_KEYS_MAX, so the
    # request reaches the file_keys CHECK and fails as a 500 instead of a clear 422.
    files = [world.file(f"ghi chú {i}".encode(), "txt", "text/plain") for i in range(20)]
    response = submit(client, world, files=files, text="thêm một ghi chú gõ tay")
    assert response.status_code == 422 and response.json()["detail"] == "bad_note"
    nothing_written(world)
    assert not [k for k in world.storage.objects if k.endswith(".txt") and "gõ" in k]


def test_stored_size_differs_from_declared_422(client: TestClient, world: World) -> None:
    # Red when: a file whose stored size is not the declared one is queued anyway.
    pdf = world.pdf()
    response = submit(client, world, files=[pdf | {"size_bytes": pdf["size_bytes"] + 1}])
    assert response.status_code == 422 and response.json()["detail"] == "size_mismatch"
    nothing_written(world)


def test_stored_checksum_differs_from_declared_422(client: TestClient, world: World) -> None:
    # Red when: the store's checksum is not compared with the declared sha256.
    pdf = world.pdf()
    key = f"users/{world.user.id}/sessions/{world.draft.id}/notes/{pdf['sha256']}.pdf"
    world.storage.checksums_hex[key] = "ee" * 32
    response = submit(client, world, files=[pdf])
    assert response.status_code == 422 and response.json()["detail"] == "content_mismatch"
    nothing_written(world)


def test_typed_text_over_the_account_quota_409_nothing_written(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: the typed text is written although the account's note quota is spent.
    monkeypatch.setenv("CORE_NOTE_QUOTA_BYTES", "5")
    get_settings.cache_clear()
    response = submit(client, world, text="mười hai byte trở lên")
    assert response.status_code == 409 and response.json()["detail"] == "storage_quota_exceeded"
    nothing_written(world)
    assert not [k for k in world.storage.objects if k.endswith(".txt")]


def test_same_file_twice_with_another_type_422(client: TestClient, world: World) -> None:
    # Red when: one sha256 is accepted under two declared types (the first silently wins).
    pdf = world.pdf()
    response = submit(client, world, files=[pdf, pdf | {"mime": "text/plain"}])
    assert response.status_code == 422 and response.json()["detail"] == "bad_note"
    nothing_written(world)


def test_typed_text_is_never_filed_under_a_binary_type(client: TestClient, world: World) -> None:
    # Red when: a file entry carrying the typed text's sha256 with a binary type makes the
    # server write the typed text under that type, with no magic-bytes check (it skips the
    # typed file). The note then claims to be a PDF and is not one.
    text = "đây là văn bản, không phải PDF"
    data = text.encode()
    liar = {"sha256": sha(data), "mime": "application/pdf", "size_bytes": len(data)}
    response = submit(client, world, files=[liar], text=text)
    assert response.status_code == 422
    nothing_written(world)


def test_typed_text_declared_size_must_be_its_real_size(client: TestClient, world: World) -> None:
    # Red when: a file entry carrying the typed text's sha256 with a smaller size_bytes is
    # trusted, so the note's size (and the quota that sums it) understates the stored text.
    data = ("x" * 5000).encode()
    liar = {"sha256": sha(data), "mime": "text/plain", "size_bytes": 1}
    response = submit(client, world, files=[liar], text=data.decode())
    assert response.status_code == 422 and response.json()["detail"] == "bad_note"
    nothing_written(world)


# --- Rate limits ------------------------------------------------------------------------------


def test_submitting_too_often_is_a_429(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: POST /v1/submissions has no per-user rate limit.
    monkeypatch.setenv("CORE_SUBMISSIONS_PER_HOUR", "1")
    get_settings.cache_clear()
    assert submit(client, world, files=[world.pdf()]).status_code == 201
    world.draft = world.new_draft()
    response = submit(client, world, files=[world.pdf()])
    assert response.status_code == 429
    assert len(events(world)) == 1


def test_making_drafts_too_often_is_a_429(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: the draft route has no per-user rate limit (review Y4).
    monkeypatch.setenv("CORE_SESSION_CREATES_PER_HOUR", "1")
    get_settings.cache_clear()
    url = f"/v1/subjects/{world.subject.id}/submission-drafts"
    assert client.post(url, headers=world.headers).status_code == 201
    assert client.post(url, headers=world.headers).status_code == 429


# --- Reserved uploads -------------------------------------------------------------------------


def test_reserved_upload_is_released_once_the_file_is_a_note(
    client: TestClient, world: World
) -> None:
    # Red when: the note_upload reservation outlives the submission, so the same bytes count
    # twice against the account quota.
    data = b"%PDF-1.7 reserved"
    digest = hashlib.sha256(data).hexdigest()
    asked = client.post(
        f"/v1/sessions/{world.draft.id}/notes/upload-url",
        json={"sha256": digest, "mime": "application/pdf", "size_bytes": len(data)},
        headers=world.headers,
    )
    assert asked.status_code == 201, asked.text
    world.upload(data, "pdf")
    held = (
        select(func.count()).select_from(NoteUpload).where(NoteUpload.session_id == world.draft.id)
    )
    assert world.db.scalar(held) == 1
    response = submit(
        client,
        world,
        files=[{"sha256": digest, "mime": "application/pdf", "size_bytes": len(data)}],
    )
    assert response.status_code == 201, response.text
    assert world.db.scalar(held) == 0
    assert world.db.scalar(select(func.count()).select_from(NoteFile)) == 1


def test_typed_text_also_uploaded_as_a_file_keeps_no_reservation(
    client: TestClient, world: World
) -> None:
    # Red when: the reservation of an uploaded .txt whose bytes equal the typed text is left in
    # note_upload (the typed sha is skipped when reservations are taken). The hourly note_cleanup
    # job then deletes that row's object, which is the submitted note itself (AC11: the file must
    # stay stored so the submission can run again).
    text = "Ghi chú buổi học: định tuyến tĩnh"
    data = text.encode()
    digest = hashlib.sha256(data).hexdigest()
    asked = client.post(
        f"/v1/sessions/{world.draft.id}/notes/upload-url",
        json={"sha256": digest, "mime": "text/plain", "size_bytes": len(data)},
        headers=world.headers,
    )
    assert asked.status_code == 201, asked.text
    world.upload(data, "txt")
    entry = {"sha256": digest, "mime": "text/plain", "size_bytes": len(data)}
    response = submit(client, world, files=[entry], text=text)
    assert response.status_code == 201, response.text
    [note] = world.db.scalars(select(NoteFile)).all()
    later = world.db.scalar(select(func.max(NoteUpload.presigned_at)))
    if later is not None:  # what the cleanup job would do once the reservation is old
        delete_abandoned_notes(world.db, world.storage, later + timedelta(days=30), timedelta(0))
    assert note.object_key in world.storage.objects
    held = (
        select(func.count()).select_from(NoteUpload).where(NoteUpload.session_id == world.draft.id)
    )
    assert world.db.scalar(held) == 0


# --- Context: the units of the mentioned scope (AC3) ------------------------------------------


def _unit_on(world: World, section_id: Any, title: str) -> Any:
    unit = make_unit(world.db, world.user, world.subject, title=title)
    world.db.add(
        UnitSection(
            user_id=world.user.id,
            subject_id=world.subject.id,
            unit_id=unit.id,
            section_id=section_id,
        )
    )
    world.db.flush()
    return unit


def _context_titles(world: World) -> set[str]:
    [event] = events(world)
    return {u["title"] for u in world.context_of(event)["existing_units"]}


def test_context_units_of_a_chapter_include_its_subsections(
    client: TestClient, world: World
) -> None:
    # Red when: the scope tree is not walked (only the chapter's own units go to the AI), or
    # units of another chapter leak in.
    sub = world.section(world.document, "3.1 Định tuyến", parent_id=world.chapter.id)
    other = world.section(world.document, "Chương 4. Tầng vận chuyển", ord=1)
    _unit_on(world, world.chapter.id, "Tầng mạng")
    _unit_on(world, sub.id, "Định tuyến")
    _unit_on(world, other.id, "TCP")
    response = submit(client, world, description="@Mạng máy tính chương 3", files=[world.pdf()])
    assert response.status_code == 201, response.text
    assert _context_titles(world) == {"Tầng mạng", "Định tuyến"}


def test_context_units_of_a_page_range_are_those_of_the_whole_document(
    client: TestClient, world: World
) -> None:
    # Red when: a page or whole-document mention sends no existing units to merge with.
    other = world.section(world.document, "Chương 4. Tầng vận chuyển", ord=1)
    _unit_on(world, world.chapter.id, "Tầng mạng")
    _unit_on(world, other.id, "TCP")
    response = submit(client, world, description="@Mạng máy tính tr. 5-7", files=[world.pdf()])
    assert response.status_code == 201, response.text
    assert _context_titles(world) == {"Tầng mạng", "TCP"}


def test_context_file_carries_resolved_scope_not_the_raw_text(
    client: TestClient, world: World
) -> None:
    # Red when: the context file stores something other than the description and resolved ids.
    response = submit(client, world, description="@Mạng máy tính chương 3", files=[world.pdf()])
    assert response.status_code == 201
    [event] = events(world)
    context = world.context_of(event)
    assert set(context) == {"version", "description", "mentions", "existing_units"}
    assert context["mentions"] == [
        {
            "document_id": str(world.document.id),
            "section_id": str(world.chapter.id),
            "first_page": 40,
            "last_page": 55,
        }
    ]
    assert event.payload["context_key"].startswith(
        f"users/{world.user.id}/sessions/{world.draft.id}/context/"
    )
    assert json.dumps(event.payload).find("Mạng") == -1
    assert world.db.scalar(select(func.count()).select_from(Submission)) == 1


@pytest.mark.parametrize(("description", "expected"), [("   ", None), ("  học  ", "học")])
def test_context_description_is_trimmed_and_blank_is_null(
    client: TestClient, world: World, description: str, expected: str | None
) -> None:
    # Red when: the context carries the description untrimmed, or a blank one as text instead
    # of null (plan N3: no description -> context.description null; the AI must not read
    # whitespace as the learner's words).
    response = submit(client, world, description=description, files=[world.pdf()])
    assert response.status_code == 201, response.text
    [event] = events(world)
    assert world.context_of(event)["description"] == expected


def test_store_down_while_writing_the_context_is_503_and_removes_the_typed_text(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: a store failure half-way leaves the typed-text object behind (no row points to
    # it, so nothing ever deletes it), or surfaces as a 500.
    real = world.storage.write

    def write(key: str, data: bytes, *, content_type: str) -> None:
        if "/context/" in key:
            raise StorageUnavailableError("down (test)")
        real(key, data, content_type=content_type)

    monkeypatch.setattr(world.storage, "write", write)
    response = submit(client, world, text="ghi chú sẽ bị xóa")
    assert response.status_code == 503 and response.json()["detail"] == "storage_unavailable"
    nothing_written(world)
    assert not [k for k in world.storage.objects if k.endswith(".txt")]
