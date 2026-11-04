"""Kho kiến thức (G1, G3, G4): subject -> session -> cards, edit/delete, source highlight."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.api.deps import get_storage
from core_api.api.vault import find_highlight
from core_api.db.models import Anchor, NoteFile, QuestionUnit, StudySession, Submission
from core_api.grading import units_of
from fake_storage import FakeStorage
from v2_rows import RUN, make_document, make_question, make_subject, make_unit


def _world(db: Session, **doc: Any):
    user, headers = signed_in(db)
    subject = make_subject(db, user)
    study = StudySession(
        user_id=user.id,
        subject_id=subject.id,
        description_raw="Chương 3: TCP\nchi tiết",
        extraction="proposed",
        status="confirmed",
        confirmed_at=datetime.now(UTC),
        studied_on=datetime.now(UTC).date(),
        learning_day=datetime.now(UTC).date(),
    )
    db.add(study)
    db.flush()
    unit = make_unit(
        db,
        user,
        subject,
        title="TCP",
        summary="Giao thức tin cậy",
        status="canonical",
        session_id=study.id,
    )
    db.add(
        Anchor(
            user_id=user.id, unit_id=unit.id, source="notes", quote_text="TCP tin cậy", run_id=RUN
        )
    )
    db.commit()
    return user, headers, subject, study, unit


def test_g1_subjects_sessions_cards(client: TestClient, db_session: Session):
    _, headers, subject, study, unit = _world(db_session)
    subjects = client.get("/v1/vault/subjects", headers=headers).json()
    assert [(s["sessions"], s["cards"]) for s in subjects] == [(1, 1)]
    sessions = client.get(f"/v1/vault/subjects/{subject.id}/sessions", headers=headers).json()
    assert (sessions[0]["title"], sessions[0]["cards"]) == ("Chương 3: TCP", 1)
    cards = client.get(f"/v1/vault/sessions/{study.id}/cards", headers=headers).json()["cards"]
    assert cards[0]["id"] == str(unit.id) and cards[0]["content"] == "Giao thức tin cậy"


def test_g1_deleted_subject_is_not_in_the_vault(client: TestClient, db_session: Session):
    _, headers, subject, _, _ = _world(db_session)
    subject.deleted_at = datetime.now(UTC)
    db_session.commit()
    assert client.get("/v1/vault/subjects", headers=headers).json() == []
    r = client.get(f"/v1/vault/subjects/{subject.id}/sessions", headers=headers)
    assert r.status_code == 404
    # A session of the deleted subject is not reachable by typing its URL either.
    study_id = db_session.query(StudySession.id).filter_by(subject_id=subject.id).scalar()
    r = client.get(f"/v1/vault/sessions/{study_id}/cards", headers=headers)
    assert r.status_code == 404


def test_g1_other_user_gets_404(client: TestClient, db_session: Session):
    _, _, subject, study, unit = _world(db_session)
    _, other = signed_in(db_session)
    assert client.get(f"/v1/vault/sessions/{study.id}/cards", headers=other).status_code == 404
    assert client.get(f"/v1/vault/subjects/{subject.id}/sessions", headers=other).status_code == 404
    r = client.patch(f"/v1/vault/cards/{unit.id}", headers=other, json={"title": "x"})
    assert r.status_code == 404


def test_g3_edit_becomes_the_grading_reference(client: TestClient, db_session: Session):
    user, headers, subject, _, unit = _world(db_session)
    q = make_question(db_session, user, subject)
    db_session.add(
        QuestionUnit(user_id=user.id, question_id=q.id, unit_id=unit.id, subject_id=subject.id)
    )
    db_session.commit()
    r = client.patch(
        f"/v1/vault/cards/{unit.id}",
        headers=headers,
        json={"title": "TCP/IP", "content": "Có bắt tay ba bước"},
    )
    assert r.status_code == 200 and r.json()["content"] == "Có bắt tay ba bước"
    db_session.expire_all()
    (graded,) = units_of(db_session, user.id, q.id)
    assert "Có bắt tay ba bước" in graded.anchors[0].quote_text
    assert graded.title == "TCP/IP"


def test_g3_delete_retires_the_card(client: TestClient, db_session: Session):
    _, headers, _, study, unit = _world(db_session)
    assert client.delete(f"/v1/vault/cards/{unit.id}", headers=headers).status_code == 204
    cards = client.get(f"/v1/vault/sessions/{study.id}/cards", headers=headers).json()["cards"]
    assert cards == []
    assert client.delete(f"/v1/vault/cards/{unit.id}", headers=headers).status_code == 404


def test_g4_source_highlights_the_passage(client: TestClient, db_session: Session):
    user, headers, subject, _, unit = _world(db_session)
    key = f"derived/{uuid.uuid4()}/page_text.json"
    document = make_document(db_session, user, subject, page_text_key=key)
    db_session.add(
        Anchor(
            user_id=user.id,
            unit_id=unit.id,
            source="document",
            document_id=document.id,
            page_no=2,
            quote_text="bắt tay  ba bước",
            run_id=RUN,
        )
    )
    db_session.commit()
    storage = FakeStorage()
    storage.write(
        key,
        json.dumps({"pages": [{"page": 2, "text": "TCP dùng bắt tay\nba bước để nối"}]}).encode(),
        content_type="application/json",
    )
    client.app.dependency_overrides[get_storage] = lambda: storage  # type: ignore[attr-defined]
    rows = client.get(f"/v1/vault/cards/{unit.id}/sources", headers=headers).json()
    doc = next(r for r in rows if r["source"] == "document")
    start, end = doc["highlight"]
    assert doc["page_text"][start:end] == "bắt tay\nba bước"
    assert "X-Amz-Expires=600" in doc["file_url"] and doc["image_url"] is None
    assert next(r for r in rows if r["source"] == "notes")["page_text"] is None
    assert next(r for r in rows if r["source"] == "notes")["file_url"] is None


def test_find_highlight():
    assert find_highlight("abc def", "def") == (4, 7)
    assert find_highlight("abc def", "xyz") is None


def test_g4_notes_source_lists_the_session_photos(client: TestClient, db_session: Session):
    user, headers, _, study, unit = _world(db_session)
    sha = "ab" * 32
    for n, mime in enumerate(("image/jpeg", "application/pdf")):
        digest = f"{n}{sha[1:]}"
        db_session.add(
            NoteFile(
                user_id=user.id,
                session_id=study.id,
                object_key=f"users/{user.id}/sessions/{study.id}/notes/{digest}.x",
                sha256=digest,
                mime=mime,
                size_bytes=5,
            )
        )
    db_session.commit()
    rows = client.get(f"/v1/vault/cards/{unit.id}/sources", headers=headers).json()
    notes = next(r for r in rows if r["source"] == "notes")
    assert len(notes["note_image_urls"]) == 1 and "X-Amz-Expires=600" in notes["note_image_urls"][0]


def test_v2_finished_session_is_listed(client: TestClient, db_session: Session):
    """A v2 session ("Hoàn thành") stays a draft row; its done submission is what finishes it.
    Red when: Kho counts or lists only v1 confirmed sessions, so the finished one is missing."""
    user, headers = signed_in(db_session)
    subject = make_subject(db_session, user)
    ids: dict[str, uuid.UUID] = {}
    for name, status in (("done", "done"), ("working", "processing")):
        study = StudySession(
            user_id=user.id,
            subject_id=subject.id,
            description_raw=f"Buổi {name}\nchi tiết",
            extraction="proposed",
            status="draft",
        )
        db_session.add(study)
        db_session.flush()
        ids[name] = study.id
        finished = datetime.now(UTC) if status == "done" else None
        db_session.add(
            Submission(
                user_id=user.id,
                session_id=study.id,
                status=status,
                file_keys=[],
                finished_at=finished,
            )
        )
    make_unit(
        db_session,
        user,
        subject,
        title="Thẻ",
        summary="x",
        status="canonical",
        session_id=ids["done"],
    )
    db_session.commit()
    subjects = client.get("/v1/vault/subjects", headers=headers).json()
    assert [(s["sessions"], s["cards"]) for s in subjects] == [(1, 1)]
    sessions = client.get(f"/v1/vault/subjects/{subject.id}/sessions", headers=headers).json()
    listed = [(x["id"], x["title"], x["cards"]) for x in sessions]
    assert listed == [(str(ids["done"]), "Buổi done", 1)]


def test_vault_title_prefers_study_title(client: TestClient, db_session: Session):
    # Red when: the session is still named by the first 80 characters of the note, or an old
    # session (no title) loses its fallback.
    _, headers, subject, study, _ = _world(db_session)
    study.title = "Giao thức TCP"
    db_session.commit()
    sessions = client.get(f"/v1/vault/subjects/{subject.id}/sessions", headers=headers).json()
    assert sessions[0]["title"] == "Giao thức TCP"
    cards = client.get(f"/v1/vault/sessions/{study.id}/cards", headers=headers).json()
    assert cards["title"] == "Giao thức TCP"
    study.title = None
    db_session.commit()
    sessions = client.get(f"/v1/vault/subjects/{subject.id}/sessions", headers=headers).json()
    assert sessions[0]["title"] == "Chương 3: TCP"


def test_session_result_reports_status_cards_and_notice(client: TestClient, db_session: Session):
    # Red when: a done session with no card says nothing, or another user's session answers.
    user, headers, _, study, _ = _world(db_session)
    sub = Submission(
        user_id=user.id,
        session_id=study.id,
        status="done",
        finished_at=datetime.now(UTC),
        notice="no_content_found",
    )
    db_session.add(sub)
    db_session.commit()
    body = client.get(f"/v1/vault/sessions/{study.id}/result", headers=headers).json()
    assert body["submission_status"] == "done" and body["cards"] == 1
    assert body["notice"] == "no_content_found" and body["title"] == "Chương 3: TCP"
    stranger = signed_in(db_session)[1]
    assert client.get(f"/v1/vault/sessions/{study.id}/result", headers=stranger).status_code == 404


def test_session_result_before_any_submission(client: TestClient, db_session: Session):
    _, headers, _, study, _ = _world(db_session)
    body = client.get(f"/v1/vault/sessions/{study.id}/result", headers=headers).json()
    assert body["submission_status"] is None and body["notice"] is None
