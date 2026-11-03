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
from core_api.db.models import Anchor, QuestionUnit, StudySession
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
    assert next(r for r in rows if r["source"] == "notes")["page_text"] is None


def test_find_highlight():
    assert find_highlight("abc def", "def") == (4, 7)
    assert find_highlight("abc def", "xyz") is None
