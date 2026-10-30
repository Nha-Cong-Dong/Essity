"""POST /v1/submissions (T7.6; US-02 AC2 files stored first, AC3 scopes, AC4 clear errors, AC11
queued, AC13 no @ and no description needed): one transaction, nothing written on a refusal."""

import datetime
import hashlib
import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from session_helpers import indexed_document, subject_of
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.config import get_settings
from core_api.db.models import (
    DocSection,
    NoteFile,
    Outbox,
    StudySession,
    Submission,
)
from fake_storage import FakeStorage
from v2_rows import make_section

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
PDF = b"%PDF-1.7 body"
ZIP = b"PK\x03\x04 body"
pytestmark = pytest.mark.usefixtures("fake_storage")


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CORE_SUBMISSIONS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class World:
    def __init__(self, db: Session, storage: FakeStorage) -> None:
        self.db = db
        self.storage = storage
        self.user, self.headers = signed_in(db)
        self.subject = subject_of(db, self.user)
        self.document = indexed_document(
            db, storage, self.user, self.subject, name="Mạng máy tính", pages=100
        )
        self.draft = self.new_draft()
        self.chapter = self.section(
            self.document, "Chương 3. Tầng mạng", first_page=40, last_page=55
        )

    def new_draft(self) -> StudySession:
        draft = StudySession(
            subject_id=self.subject.id, description_raw="(bài nộp)", extraction="failed"
        )
        draft.user_id = self.user.id
        self.db.add(draft)
        self.db.flush()
        return draft

    def section(self, document: Any, title: str, **kw: Any) -> DocSection:
        return make_section(self.db, self.user, document, title=title, **kw)

    def upload(self, data: bytes, ext: str, draft: StudySession | None = None) -> str:
        draft = draft or self.draft
        digest = sha(data)
        key = f"users/{self.user.id}/sessions/{draft.id}/notes/{digest}.{ext}"
        self.storage.put(key, data, None)
        return digest

    def file(self, data: bytes, ext: str, mime: str, **over: Any) -> dict[str, Any]:
        return {"sha256": self.upload(data, ext), "mime": mime, "size_bytes": len(data)} | over

    def pdf(self) -> dict[str, Any]:
        return self.file(PDF, "pdf", "application/pdf")

    def events(self) -> list[Outbox]:
        return list(
            self.db.scalars(select(Outbox).where(Outbox.event_type == "submission.created.v1"))
        )

    def context_of(self, event: Outbox) -> dict[str, Any]:
        raw = self.storage.objects[event.payload["context_key"]][0]
        return json.loads(raw)


@pytest.fixture
def world(db_session: Session, fake_storage: FakeStorage) -> World:
    return World(db_session, fake_storage)


def submit(client: TestClient, world: World, **body: Any) -> Any:
    body = {"session_id": str(world.draft.id)} | body
    return client.post("/v1/submissions", json=body, headers=world.headers)


def nothing_written(world: World) -> None:
    db = world.db
    assert world.events() == []
    assert db.scalar(select(func.count()).select_from(Submission)) == 0
    assert db.scalar(select(func.count()).select_from(NoteFile)) == 0
    assert not [k for k in world.storage.objects if "/context/" in k]


# --- Off, and on --------------------------------------------------------------------------------


def test_flag_off_404_and_nothing_published(client: TestClient, world: World) -> None:
    # Red when: the route is reachable (or publishes) before ai-service can handle the event.
    response = submit(client, world, files=[world.pdf()])
    assert response.status_code == 404
    nothing_written(world)
    drafts = client.post(
        f"/v1/subjects/{world.subject.id}/submission-drafts", headers=world.headers
    )
    assert drafts.status_code == 404


@pytest.mark.usefixtures("enabled")
def test_flag_on_publishes_submission_created(client: TestClient, world: World) -> None:
    description = "Hôm nay tôi học @Mạng máy tính chương 3 rất kỹ"
    response = submit(client, world, description=description, files=[world.pdf()])

    assert response.status_code == 201, response.text
    out = response.json()
    assert out["status"] == "queued"
    assert out["mentions"] == [
        {
            "document_id": str(world.document.id),
            "section_id": str(world.chapter.id),
            "first_page": 40,
            "last_page": 55,
        }
    ]
    [event] = world.events()
    payload = event.payload
    assert payload["submission_id"] == out["submission_id"]
    assert payload["study_session_id"] == str(world.draft.id)
    assert payload["subject_id"] == str(world.subject.id)
    assert [f["mime"] for f in payload["file_keys"]] == ["application/pdf"]
    # The learner's words travel in the context file, never in the event.
    assert "tôi học" not in json.dumps(payload)
    context = world.context_of(event)
    assert context["description"] == description
    assert context["mentions"][0]["first_page"] == 40
    row = world.db.scalars(select(Submission)).one()
    assert row.status == "queued" and row.file_keys == [payload["file_keys"][0]["object_key"]]
    world.db.refresh(world.draft)
    assert world.draft.description_raw == description


@pytest.mark.usefixtures("enabled")
def test_submit_without_at_and_without_description(client: TestClient, world: World) -> None:
    # Red when: the route insists on a description or an @ (AC13).
    response = submit(client, world, files=[world.pdf()])
    assert response.status_code == 201
    [event] = world.events()
    context = world.context_of(event)
    assert context["description"] is None and context["mentions"] == []


@pytest.mark.usefixtures("enabled")
def test_each_type_jpg_png_pdf_docx_pptx_text_txt_md(client: TestClient, world: World) -> None:
    files = [
        world.file(b"\xff\xd8\xff jpg", "jpg", "image/jpeg"),
        world.file(b"\x89PNG\r\n\x1a\n png", "png", "image/png"),
        world.pdf(),
        world.file(ZIP + b"d", "docx", DOCX),
        world.file(ZIP + b"p", "pptx", PPTX),
        world.file(b"plain", "txt", "text/plain"),
        world.file(b"# md", "md", "text/markdown"),
    ]
    response = submit(client, world, files=files, text="ghi chú gõ tay")
    assert response.status_code == 201, response.text
    [event] = world.events()
    mimes = sorted(f["mime"] for f in event.payload["file_keys"])
    assert mimes == sorted(
        ["image/jpeg", "image/png", "application/pdf", DOCX, PPTX, "text/plain"] * 1
        + ["text/markdown", "text/plain"]
    )
    for item in event.payload["file_keys"]:
        assert item["object_key"] in world.storage.objects


@pytest.mark.usefixtures("enabled")
def test_files_in_storage_before_event(client: TestClient, world: World) -> None:
    # Red when: an event is queued for a file that is not stored (AC2).
    missing = {"sha256": "cd" * 32, "mime": "application/pdf", "size_bytes": 5}
    response = submit(client, world, files=[missing])
    assert response.status_code == 409 and response.json()["detail"] == "upload_incomplete"
    nothing_written(world)


@pytest.mark.usefixtures("enabled")
def test_typed_text_is_stored_as_a_text_file_of_the_session(
    client: TestClient, world: World
) -> None:
    text = "định tuyến là gì"
    response = submit(client, world, text=text)
    assert response.status_code == 201, response.text
    [event] = world.events()
    [item] = event.payload["file_keys"]
    assert item["mime"] == "text/plain"
    assert world.storage.objects[item["object_key"]][0] == text.encode()
    assert item["object_key"].endswith(f"/notes/{sha(text.encode())}.txt")


@pytest.mark.usefixtures("enabled")
def test_rollback_when_enqueue_fails_leaves_no_row_and_no_text_object(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.db.commit()

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("outbox down")

    monkeypatch.setattr("core_api.api.submissions.enqueue_event", boom)
    with pytest.raises(RuntimeError):
        submit(client, world, text="ghi chú")
    world.db.rollback()
    assert world.events() == []
    assert world.db.scalar(select(func.count()).select_from(Submission)) == 0
    assert not [k for k in world.storage.objects if k.endswith(".txt")]


@pytest.mark.usefixtures("enabled")
def test_submitting_twice_returns_the_first_and_announces_once(
    client: TestClient, world: World
) -> None:
    first = submit(client, world, files=[world.pdf()])
    second = submit(client, world, files=[world.pdf()])
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["submission_id"] == first.json()["submission_id"]
    assert len(world.events()) == 1


# --- Mentions (AC3, AC4) ----------------------------------------------------------------------


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize(
    ("description", "code", "part"),
    [
        ("@Mạng máy tính chương 9", "scope_not_found", "chuong 9"),
        ("@Mạng máy tính tr. 150-160", "scope_out_of_range", "tr. 150-160"),
        ("@Mạng máy tính slide 3", "scope_unsupported", "slide 3"),
        ("@Vật lý", "mention_not_found", "vat"),
    ],
)
def test_unresolved_mentions_are_422_naming_the_part_and_write_nothing(
    client: TestClient, world: World, description: str, code: str, part: str
) -> None:
    # Red when: an unknown name or scope is guessed, or the error does not say which part (AC4).
    response = submit(client, world, description=description, files=[world.pdf()])
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert (detail["code"], detail["mention"], detail["part"]) == (code, 0, part)
    nothing_written(world)


@pytest.mark.usefixtures("enabled")
def test_ambiguous_name_422_lists_candidates(client: TestClient, world: World) -> None:
    twin = indexed_document(
        world.db, world.storage, world.user, world.subject, name="mạng máy tính", sha="ef" * 32
    )
    response = submit(client, world, description="@Mạng máy tính", files=[world.pdf()])
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "mention_ambiguous"
    assert detail["candidates"] == sorted([str(world.document.id), str(twin.id)])
    nothing_written(world)


@pytest.mark.usefixtures("enabled")
def test_mention_by_document_id_resolves_despite_ambiguous_name(
    client: TestClient, world: World
) -> None:
    indexed_document(
        world.db, world.storage, world.user, world.subject, name="mạng máy tính", sha="ef" * 32
    )
    mention = {"document_id": str(world.document.id), "start": 0, "end": 15}
    response = submit(
        client, world, description="@Mạng máy tính tr. 5-7", mentions=[mention], files=[world.pdf()]
    )
    assert response.status_code == 201, response.text
    assert response.json()["mentions"][0]["document_id"] == str(world.document.id)
    # The helper's labels are one behind the file: printed page 5 is file page 6.
    assert response.json()["mentions"][0]["first_page"] == 6


@pytest.mark.usefixtures("enabled")
def test_mention_document_id_of_other_user_404(client: TestClient, world: World) -> None:
    other, _ = signed_in(world.db)
    other_subject = subject_of(world.db, other)
    foreign = indexed_document(world.db, world.storage, other, other_subject)
    mention = {"document_id": str(foreign.id), "start": 0, "end": 4}
    response = submit(client, world, description="@Chương", mentions=[mention], files=[world.pdf()])
    assert response.status_code == 404 and response.json()["detail"] == "document_not_found"
    nothing_written(world)


@pytest.mark.usefixtures("enabled")
def test_resolution_at_submit_not_review(client: TestClient, world: World) -> None:
    # Red when: the context follows the outline as edited after the submission.
    response = submit(client, world, description="@Mạng máy tính chương 3", files=[world.pdf()])
    assert response.status_code == 201
    [event] = world.events()
    before = world.context_of(event)
    world.chapter.first_page, world.chapter.last_page = 1, 2
    world.db.flush()
    assert world.context_of(event) == before


# --- Safety -------------------------------------------------------------------------------------


@pytest.mark.usefixtures("enabled")
def test_other_users_session_404(client: TestClient, world: World) -> None:
    _, headers = signed_in(world.db)
    response = client.post(
        "/v1/submissions",
        json={"session_id": str(world.draft.id), "files": [world.pdf()]},
        headers=headers,
    )
    assert response.status_code == 404 and response.json()["detail"] == "session_not_found"
    nothing_written(world)


@pytest.mark.usefixtures("enabled")
def test_unverified_user_403_no_event(client: TestClient, world: World) -> None:
    _, headers = signed_in(world.db, verified=False)
    response = client.post(
        "/v1/submissions", json={"session_id": str(world.draft.id)}, headers=headers
    )
    assert response.status_code == 403
    assert world.events() == []


@pytest.mark.usefixtures("enabled")
def test_magic_bytes_mismatch_422(client: TestClient, world: World) -> None:
    liar = world.file(b"not a zip", "docx", DOCX)
    response = submit(client, world, files=[liar])
    assert response.status_code == 422 and response.json()["detail"] == "content_mismatch"
    nothing_written(world)


@pytest.mark.usefixtures("enabled")
def test_text_over_limit_422_nothing_written(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CORE_NOTE_MAX_BYTES", "10")
    get_settings.cache_clear()
    response = submit(client, world, text="x" * 11)
    assert response.status_code == 422 and response.json()["detail"] == "text_too_long"
    nothing_written(world)
    assert not [k for k in world.storage.objects if k.endswith(".txt")]


@pytest.mark.usefixtures("enabled")
def test_description_over_max_422(client: TestClient, world: World) -> None:
    response = submit(client, world, description="a" * 2001, files=[world.pdf()])
    assert response.status_code == 422
    nothing_written(world)


@pytest.mark.usefixtures("enabled")
def test_nothing_handed_in_is_422(client: TestClient, world: World) -> None:
    response = submit(client, world, description="@Mạng máy tính")
    assert response.status_code == 422 and response.json()["detail"] == "nothing_submitted"


@pytest.mark.usefixtures("enabled")
def test_no_description_text_or_key_in_logs(
    client: TestClient, world: World, log_output: Callable[[], str]
) -> None:
    # Red when: a log line carries what the learner wrote, a storage key or a hash (ADR-0013).
    secret = "bí-mật-của-người-học"
    pdf = world.pdf()
    response = submit(client, world, description=f"{secret} @Mạng máy tính", files=[pdf])
    assert response.status_code == 201
    lines = [json.loads(line) for line in log_output().splitlines() if line.strip()]
    flat = json.dumps(lines, ensure_ascii=False)
    assert secret not in flat
    assert pdf["sha256"] not in flat
    assert "/notes/" not in flat and "/context/" not in flat


# --- v1 beside v2 (P1, P2) --------------------------------------------------------------------


@pytest.mark.usefixtures("enabled")
def test_v1_confirm_rejects_docx_note(client: TestClient, world: World) -> None:
    digest = world.upload(ZIP, "docx")
    response = client.post(
        f"/v1/sessions/{world.draft.id}/confirm",
        json={"notes": [{"sha256": digest, "mime": DOCX, "size_bytes": len(ZIP)}]},
        headers=world.headers,
    )
    assert response.status_code == 422


@pytest.mark.usefixtures("enabled")
def test_v1_confirm_after_submission_409_no_event(client: TestClient, world: World) -> None:
    assert submit(client, world, files=[world.pdf()]).status_code == 201
    response = client.post(f"/v1/sessions/{world.draft.id}/confirm", json={}, headers=world.headers)
    assert response.status_code == 409 and response.json()["detail"] == "submission_exists"
    confirmed = world.db.scalars(
        select(Outbox).where(Outbox.event_type == "session.confirmed.v1")
    ).all()
    assert confirmed == []


@pytest.mark.usefixtures("enabled")
def test_submission_on_confirmed_session_409(client: TestClient, world: World) -> None:
    world.draft.status = "confirmed"
    world.draft.studied_on = world.draft.learning_day = datetime.date(2026, 10, 22)
    world.draft.confirmed_at = FROZEN_NOW
    world.db.flush()
    response = submit(client, world, files=[world.pdf()])
    assert response.status_code == 409 and response.json()["detail"] == "session_confirmed"
    assert world.events() == []


@pytest.mark.usefixtures("enabled")
def test_draft_route_makes_a_draft_session_of_the_subject(client: TestClient, world: World) -> None:
    response = client.post(
        f"/v1/subjects/{world.subject.id}/submission-drafts", headers=world.headers
    )
    assert response.status_code == 201
    row = world.db.get(StudySession, uuid.UUID(response.json()["session_id"]))
    assert row is not None and row.status == "draft" and row.subject_id == world.subject.id
    other = client.post(f"/v1/subjects/{uuid.uuid4()}/submission-drafts", headers=world.headers)
    assert other.status_code == 404


@pytest.mark.usefixtures("enabled")
@pytest.mark.parametrize("scope", ["tr.5-7", "p.5-7", "trang5-7", "tr. 5-7"])
def test_pages_use_labels_whatever_the_spacing(
    client: TestClient, world: World, scope: str
) -> None:
    # Red when: labels are loaded only for some spellings, so a printed number is silently
    # taken as a file position (review R1). The helper's labels are one behind the file.
    response = submit(client, world, description=f"@Mạng máy tính {scope}", files=[world.pdf()])
    assert response.status_code == 201, response.text
    assert response.json()["mentions"][0]["first_page"] == 6


@pytest.mark.usefixtures("enabled")
def test_labels_unreadable_is_503_not_a_guess(client: TestClient, world: World) -> None:
    files = [world.pdf()]
    world.storage.down = True
    response = submit(client, world, description="@Mạng máy tính tr. 5", files=files)
    assert response.status_code == 503
    nothing_written(world)


@pytest.mark.usefixtures("enabled")
def test_rollback_leaves_no_context_file(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.db.commit()

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("outbox down")

    monkeypatch.setattr("core_api.api.submissions.enqueue_event", boom)
    files = [world.pdf()]
    with pytest.raises(RuntimeError):
        submit(client, world, files=files)
    assert not [k for k in world.storage.objects if "/context/" in k]


@pytest.mark.usefixtures("enabled")
def test_mention_document_of_another_subject_of_the_same_user_404(
    client: TestClient, world: World
) -> None:
    other_subject = subject_of(world.db, world.user)
    foreign = indexed_document(
        world.db, world.storage, world.user, other_subject, name="Khác", sha="ef" * 32
    )
    mention = {"document_id": str(foreign.id), "start": 0, "end": 5}
    response = submit(client, world, description="@Khác", mentions=[mention], files=[world.pdf()])
    assert response.status_code == 404 and response.json()["detail"] == "document_not_found"


@pytest.mark.usefixtures("enabled")
def test_draft_route_other_users_subject_404(client: TestClient, world: World) -> None:
    other, _ = signed_in(world.db)
    foreign = subject_of(world.db, other)
    response = client.post(f"/v1/subjects/{foreign.id}/submission-drafts", headers=world.headers)
    assert response.status_code == 404


def test_upload_url_refuses_docx_while_the_flag_is_off(client: TestClient, world: World) -> None:
    response = client.post(
        f"/v1/sessions/{world.draft.id}/notes/upload-url",
        json={"sha256": "ab" * 32, "mime": DOCX, "size_bytes": 10},
        headers=world.headers,
    )
    assert response.status_code == 422
