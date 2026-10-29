"""POST /v1/sessions/{id}/confirm (T4.12, US-02 AC7, AC10, AC13): one transaction writes the
ranges, the notes, the dates and the outbox event; any failure leaves a draft."""

import datetime
import json
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from session_helpers import indexed_document, subject_of
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import (
    Document,
    KnowledgeUnit,
    NoteFile,
    Outbox,
    SessionRange,
    StudySession,
    Subject,
    User,
)
from core_api.repositories.subject import SubjectRepository
from fake_storage import FakeStorage

SENTENCE = "hôm qua tôi học chương 3"
SHA = "ab" * 32
pytestmark = pytest.mark.usefixtures("fake_storage")


def draft_of(db: Session, user: User, subject: Subject) -> StudySession:
    draft = StudySession(subject_id=subject.id, description_raw=SENTENCE, extraction="proposed")
    draft.user_id = user.id
    db.add(draft)
    db.flush()
    return draft


def range_of(document: Document, first: int = 3, last: int = 9, **over: Any) -> dict[str, Any]:
    return {
        "document_id": str(document.id),
        "start_page": first,
        "end_page": last,
        "depth": "deep",
    } | over


def put_note(storage: FakeStorage, user: User, draft: StudySession, sha: str = SHA) -> None:
    storage.put(f"users/{user.id}/sessions/{draft.id}/notes/{sha}.jpg", b"x" * 10, None)


def note(sha: str = SHA, **over: Any) -> dict[str, Any]:
    return {"sha256": sha, "mime": "image/jpeg", "size_bytes": 10} | over


def confirm(client: TestClient, headers: dict[str, str], draft: StudySession, **body: Any) -> Any:
    return client.post(f"/v1/sessions/{draft.id}/confirm", json=body, headers=headers)


def outbox(db: Session) -> list[Outbox]:
    return list(db.scalars(select(Outbox).where(Outbox.event_type == "session.confirmed.v1")))


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


class World:
    def __init__(self, db: Session, storage: FakeStorage) -> None:
        self.db = db
        self.user, self.headers = signed_in(db)
        self.subject = subject_of(db, self.user)
        self.document = indexed_document(db, storage, self.user, self.subject)
        self.draft = draft_of(db, self.user, self.subject)
        self.storage = storage


@pytest.fixture
def world(db_session: Session, fake_storage: FakeStorage) -> World:
    return World(db_session, fake_storage)


def test_confirm_writes_session_ranges_notes_outbox_atomically(
    client: TestClient, world: World
) -> None:
    put_note(world.storage, world.user, world.draft)

    response = confirm(
        client,
        world.headers,
        world.draft,
        studied_on="2026-10-22",
        ranges=[range_of(world.document, start_label="2", end_label="8")],
        notes=[note()],
    )

    assert response.status_code == 200
    out = response.json()
    assert out["status"] == "confirmed"
    assert out["studied_on"] == "2026-10-22"
    assert out["ranges"][0]["start_label"] == "2"
    assert out["notes"] == [{"sha256": SHA, "mime": "image/jpeg", "size_bytes": 10}]
    db = world.db
    db.refresh(world.draft)
    assert world.draft.status == "confirmed"
    assert world.draft.description_raw == SENTENCE
    assert count(db, SessionRange) == 1
    assert count(db, NoteFile) == 1
    [event] = outbox(db)
    payload = event.payload
    assert payload["study_session_id"] == str(world.draft.id)
    assert payload["ranges"] == [
        {"document_id": str(world.document.id), "first": 3, "last": 9, "depth": "deep"}
    ]
    key = f"users/{world.user.id}/sessions/{world.draft.id}/notes/{SHA}.jpg"
    assert payload["notes"] == [{"object_key": key, "mime": "image/jpeg"}]
    assert "description" not in json.dumps(payload)
    assert SENTENCE not in json.dumps(payload)


def test_confirm_rolls_back_all_when_enqueue_fails(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    put_note(world.storage, world.user, world.draft)
    world.db.commit()

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("outbox down")

    monkeypatch.setattr("core_api.api.session_confirm.enqueue_event", boom)
    with pytest.raises(RuntimeError):
        confirm(
            client, world.headers, world.draft, ranges=[range_of(world.document)], notes=[note()]
        )
    world.db.rollback()  # what the request's own session does on an exception

    assert count(world.db, SessionRange) == 0
    assert count(world.db, NoteFile) == 0
    assert outbox(world.db) == []
    assert world.db.scalar(select(StudySession.status)) == "draft"


def test_unverified_cannot_confirm_no_outbox(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    user, headers = signed_in(db_session, verified=False)
    subject = subject_of(db_session, user)
    draft = draft_of(db_session, user, subject)

    response = confirm(client, headers, draft)

    assert response.status_code == 403
    assert outbox(db_session) == []
    assert draft.status == "draft"


def test_other_user_session_404(client: TestClient, world: World) -> None:
    _, other = signed_in(world.db)

    response = confirm(client, other, world.draft)

    assert response.status_code == 404
    assert response.json()["detail"] == "session_not_found"
    assert outbox(world.db) == []


def test_foreign_document_404(client: TestClient, world: World) -> None:
    other_user, _ = signed_in(world.db)
    other_subject = subject_of(world.db, other_user)
    foreign = indexed_document(world.db, world.storage, other_user, other_subject, sha="ef" * 32)
    second = subject_of(world.db, world.user)
    elsewhere = indexed_document(world.db, world.storage, world.user, second, sha="12" * 32)

    for document in (foreign, elsewhere):
        response = confirm(client, world.headers, world.draft, ranges=[range_of(document)])
        assert response.status_code == 404
        assert response.json()["detail"] == "document_not_found"
    assert outbox(world.db) == []
    assert count(world.db, SessionRange) == 0


def test_a_document_not_indexed_is_409(client: TestClient, world: World) -> None:
    world.document.status = "failed"
    world.document.failure_reason = "unreadable"
    world.document.toc_key = world.document.page_labels_key = None
    world.document.page_text_key = world.document.thumbnails_prefix = None
    world.document.run_id = None
    world.document.page_count = None
    world.db.flush()

    response = confirm(client, world.headers, world.draft, ranges=[range_of(world.document)])

    assert response.status_code == 409
    assert response.json()["detail"] == "not_indexed"


@pytest.mark.parametrize(
    ("first", "last"),
    [(9, 3), (0, 3), (3, 41), (41, 41)],
    ids=["reversed", "zero", "beyond", "past"],
)
def test_page_range_first_le_last_before_enqueue(
    client: TestClient, world: World, first: int, last: int
) -> None:
    response = confirm(
        client, world.headers, world.draft, ranges=[range_of(world.document, first, last)]
    )

    assert response.status_code == 422
    assert outbox(world.db) == []
    assert count(world.db, SessionRange) == 0
    assert world.draft.status == "draft"


def test_a_range_twice_is_refused(client: TestClient, world: World) -> None:
    ranges = [range_of(world.document), range_of(world.document)]

    assert confirm(client, world.headers, world.draft, ranges=ranges).status_code == 422


def test_more_than_six_ranges_is_422(client: TestClient, world: World) -> None:
    ranges = [range_of(world.document, n, n + 1) for n in range(1, 8)]

    assert confirm(client, world.headers, world.draft, ranges=ranges).status_code == 422


def test_ranges_keep_their_order_in_the_event(client: TestClient, world: World) -> None:
    ranges = [range_of(world.document, 20, 25, depth="skim"), range_of(world.document, 3, 9)]

    confirm(client, world.headers, world.draft, ranges=ranges)

    [event] = outbox(world.db)
    assert [(r["first"], r["depth"]) for r in event.payload["ranges"]] == [
        (20, "skim"),
        (3, "deep"),
    ]
    rows = world.db.scalars(select(SessionRange).order_by(SessionRange.position)).all()
    assert [r.start_page for r in rows] == [20, 3]


def test_notes_only_session_has_no_ranges_ac10(client: TestClient, world: World) -> None:
    response = confirm(client, world.headers, world.draft)

    assert response.status_code == 200
    assert response.json()["ranges"] == []
    [event] = outbox(world.db)
    assert event.payload["ranges"] == []
    assert event.payload["notes"] == []


def test_existing_units_summary_cut_2000_skipped_excluded(client: TestClient, world: World) -> None:
    def unit(title: str, summary: str, **fields: Any) -> KnowledgeUnit:
        row = KnowledgeUnit(
            subject_id=world.subject.id,
            title=title,
            summary=summary,
            kind="concept",
            run_id=uuid.uuid4(),
            **fields,
        )
        row.user_id = world.user.id
        world.db.add(row)
        return row

    long = unit("Dài", "ế" * 5000)
    unit("Bỏ qua", "x", skipped_at=FROZEN_NOW)
    unit("Đã gộp", "x", status="merged")
    world.db.flush()

    confirm(client, world.headers, world.draft)

    [event] = outbox(world.db)
    [sent] = event.payload["existing_units"]
    assert sent["unit_id"] == str(long.id)
    assert sent["summary"] == "ế" * 2000


def test_confirm_twice_one_outbox_row(client: TestClient, world: World) -> None:
    body: dict[str, Any] = {"ranges": [range_of(world.document)]}

    first = confirm(client, world.headers, world.draft, **body)
    again = confirm(client, world.headers, world.draft, ranges=[range_of(world.document, 1, 2)])

    assert first.status_code == again.status_code == 200
    assert again.json() == first.json()
    assert len(outbox(world.db)) == 1
    assert count(world.db, SessionRange) == 1


def test_late_log_keeps_studied_on_and_learning_day(client: TestClient, world: World) -> None:
    response = confirm(client, world.headers, world.draft, studied_on="2026-10-17")

    out = response.json()
    assert out["studied_on"] == "2026-10-17"
    assert out["learning_day"] == "2026-10-22"  # FROZEN_NOW is before 04:00 on the 23rd (HCMC)
    assert world.draft.studied_on == datetime.date(2026, 10, 17)


def test_no_date_means_today(client: TestClient, world: World) -> None:
    assert confirm(client, world.headers, world.draft).json()["studied_on"] == "2026-10-22"


@pytest.mark.parametrize("day", ["2026-10-23", "2025-10-20"], ids=["future", "too-old"])
def test_a_date_outside_the_window_is_422(client: TestClient, world: World, day: str) -> None:
    response = confirm(client, world.headers, world.draft, studied_on=day)

    assert response.status_code == 422
    assert response.json()["detail"] == "bad_date"
    assert outbox(world.db) == []


def test_same_note_sha_one_row(client: TestClient, world: World) -> None:
    put_note(world.storage, world.user, world.draft)

    response = confirm(client, world.headers, world.draft, notes=[note(), note()])

    assert response.status_code == 200
    assert count(world.db, NoteFile) == 1
    assert len(outbox(world.db)[0].payload["notes"]) == 1


def test_the_same_sha_with_another_type_is_422(client: TestClient, world: World) -> None:
    put_note(world.storage, world.user, world.draft)

    response = confirm(client, world.headers, world.draft, notes=[note(), note(mime="image/png")])

    assert response.status_code == 422
    assert response.json()["detail"] == "bad_note"


def test_note_missing_in_storage_409(client: TestClient, world: World) -> None:
    response = confirm(
        client, world.headers, world.draft, ranges=[range_of(world.document)], notes=[note()]
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "upload_incomplete"
    assert count(world.db, SessionRange) == 0
    assert outbox(world.db) == []


def test_note_with_the_wrong_size_is_422(client: TestClient, world: World) -> None:
    put_note(world.storage, world.user, world.draft)

    response = confirm(client, world.headers, world.draft, notes=[note(size_bytes=11)])

    assert response.status_code == 422
    assert response.json()["detail"] == "size_mismatch"
    assert count(world.db, NoteFile) == 0


def test_note_stored_with_another_hash_is_422(client: TestClient, world: World) -> None:
    put_note(world.storage, world.user, world.draft)
    key = f"users/{world.user.id}/sessions/{world.draft.id}/notes/{SHA}.jpg"
    world.storage.checksums_hex[key] = "cd" * 32

    response = confirm(client, world.headers, world.draft, notes=[note()])

    assert response.status_code == 422
    assert response.json()["detail"] == "content_mismatch"


def test_storage_down_is_503_and_nothing_is_written(client: TestClient, world: World) -> None:
    put_note(world.storage, world.user, world.draft)
    world.storage.down = True

    response = confirm(client, world.headers, world.draft, notes=[note()])

    assert response.status_code == 503
    assert world.draft.status == "draft"
    assert outbox(world.db) == []


def test_a_deleted_subject_is_404(client: TestClient, world: World) -> None:
    SubjectRepository(world.db, world.user.id).soft_delete(world.subject.id, FROZEN_NOW)

    response = confirm(client, world.headers, world.draft)

    assert response.status_code == 404
    assert response.json()["detail"] == "subject_not_found"


@pytest.mark.parametrize(
    "body",
    [
        {"ranges": [{"document_id": "x", "start_page": 1, "end_page": 2, "depth": "deep"}]},
        {
            "notes": [
                {"object_key": "users/x", "sha256": SHA, "mime": "image/jpeg", "size_bytes": 1}
            ]
        },
        {"notes": [{"sha256": "AB" * 32, "mime": "image/jpeg", "size_bytes": 1}]},
        {"notes": [{"sha256": SHA, "mime": "image/gif", "size_bytes": 1}]},
        {"notes": [note(size_bytes=0)]},
        {"studied_on": "yesterday"},
        {"description": "đổi mô tả"},
    ],
)
def test_a_malformed_body_is_422(client: TestClient, world: World, body: dict[str, Any]) -> None:
    assert confirm(client, world.headers, world.draft, **body).status_code == 422
    assert outbox(world.db) == []


def test_the_description_is_never_changed(client: TestClient, world: World) -> None:
    confirm(client, world.headers, world.draft, ranges=[range_of(world.document)])

    assert world.db.scalar(select(StudySession.description_raw)) == SENTENCE


def test_no_description_in_the_log(
    client: TestClient, world: World, log_output: Callable[[], str]
) -> None:
    confirm(client, world.headers, world.draft)

    assert SENTENCE not in log_output()
