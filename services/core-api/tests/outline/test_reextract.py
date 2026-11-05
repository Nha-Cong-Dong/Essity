"""OUTLINE-FIX3: "Tách lại đề cương". The outline is read again and laid over the one the
learner has worked on: what they covered, excluded or edited stays; the new reading's fixes land.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from outline_rows import document_in, subject_of, with_outline
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import DocSection, Document, Outbox, UnitSection, User
from core_api.handlers.document_indexed import OnDocumentIndexed, on_document_failed
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.doc_section import DocSectionRepository, NewSection
from core_api.services.outline import OutlineService
from documents.test_document_indexed import failed_event, indexed_event
from fake_storage import FakeStorage
from v2_rows import make_unit

pytestmark = pytest.mark.usefixtures("fake_storage")

OLD = [
    NewSection("1. Xác suất", None, 1, 20, 20, "page", "heading"),
    NewSection("1.1. Biến cố", 0, 1, 10, 10, "page", "heading"),
    NewSection("1.2. Quy luật chuẩn N(a,σ2", 0, 11, 20, 10, "page", "heading"),
    NewSection(")", None, 21, 30, 10, "page", "heading"),
    NewSection("2. Ước lượng", None, 31, 40, 10, "page", "heading"),
]


def node(title: str, parent: int | None, start: int, end: int) -> dict[str, Any]:
    return {
        "title": title,
        "parent": parent,
        "page_start": start,
        "page_end": end,
        "weight": end - start + 1,
        "source": "heading",
    }


NEW = {
    "unit": "page",
    "nodes": [
        node("1. Xác suất", None, 1, 20),
        node("1.1. Biến cố", 0, 1, 10),
        node("1.2. Quy luật chuẩn N(a,σ2)", 0, 11, 20),
        node("2. Ước lượng", None, 31, 40),
        node("3. Ý nghĩa", None, 41, 50),
    ],
}


def answer(storage: FakeStorage, document: Document, body: Any = NEW) -> Any:
    event = indexed_event(document, payload={"page_count": 50})
    key = event.payload.toc_key.rsplit("/", 1)[0] + "/outline.json"
    storage.objects[key] = (json.dumps(body).encode(), None)
    return event


def reread(session: Session, storage: FakeStorage, user: Any, document: Document) -> None:
    OutlineService(session, user.id).request_reextract(document.id)
    OnDocumentIndexed(storage)(session, answer(storage, document))
    session.flush()


def rows(session: Session, user: Any, document: Document) -> dict[str, DocSection]:
    return {r.title: r for r in DocSectionRepository(session, user.id).of_document(document.id)}


def worked(session: Session) -> tuple[Any, dict[str, str], Document, dict[str, DocSection]]:
    user, headers = signed_in(session)
    document = document_in(session, user, subject_of(session, user), pages=50)
    by_title = with_outline(session, user, document, OLD)
    OutlineService(session, user.id).edit_section(by_title["1.1. Biến cố"].id, studied=True)
    return user, headers, document, by_title


def test_the_reading_is_laid_over_the_learners_work(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user, _, document, before = worked(db_session)
    studied_id = before["1.1. Biến cố"].id
    fixed_id = before["1.2. Quy luật chuẩn N(a,σ2"].id

    reread(db_session, fake_storage, user, document)

    after = rows(db_session, user, document)
    assert after["1.1. Biến cố"].id == studied_id
    assert after["1.1. Biến cố"].studied_weight == 10  # still studied
    assert after["1.2. Quy luật chuẩn N(a,σ2)"].id == fixed_id  # fixed title, same row
    assert ")" not in after  # nothing hung on it: gone
    assert after["3. Ý nghĩa"].parent_id is None
    assert after["1.1. Biến cố"].parent_id == after["1. Xác suất"].id
    current = db_session.get(Document, document.id)
    assert current is not None and current.status == "indexed" and current.reread is None


def test_an_old_section_with_a_card_is_kept_and_excluded(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user, _, document, before = worked(db_session)
    garbage = before[")"]
    unit = make_unit(db_session, user, subject_of_id(garbage), status="canonical")  # pyright: ignore[reportArgumentType]
    link = UnitSection(subject_id=garbage.subject_id, unit_id=unit.id, section_id=garbage.id)
    link.user_id = user.id
    db_session.add(link)
    db_session.flush()

    reread(db_session, fake_storage, user, document)

    kept = rows(db_session, user, document)[")"]
    assert kept.id == garbage.id and kept.excluded
    assert db_session.scalar(select(func.count()).select_from(UnitSection)) == 1


def test_an_edited_range_stays_but_the_title_is_fixed(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user, _, document, before = worked(db_session)
    OutlineService(db_session, user.id).edit_section(
        before["1.2. Quy luật chuẩn N(a,σ2"].id, first_page=12, last_page=20
    )

    reread(db_session, fake_storage, user, document)

    section = rows(db_session, user, document)["1.2. Quy luật chuẩn N(a,σ2)"]
    assert (section.first_page, section.last_page, section.source) == (12, 20, "user")


def test_the_same_answer_twice_changes_nothing(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user, _, document, _ = worked(db_session)
    reread(db_session, fake_storage, user, document)
    first = {
        t: (r.id, r.parent_id, r.first_page) for t, r in rows(db_session, user, document).items()
    }

    reread(db_session, fake_storage, user, document)

    assert {
        t: (r.id, r.parent_id, r.first_page) for t, r in rows(db_session, user, document).items()
    } == first


def subject_of_id(section: DocSection) -> Any:
    class _S:
        id = section.subject_id

    return _S()


# --- HTTP ----------------------------------------------------------------------------------


def test_post_marks_the_document_being_read_and_sends_the_event(
    client: TestClient, db_session: Session
) -> None:
    _, headers, document, _ = worked(db_session)

    response = client.post(f"/v1/documents/{document.id}/reextract-outline", headers=headers)

    assert response.status_code == 202
    assert response.json()["status"] == "indexed"  # nothing is taken away while it is read
    db_session.expire_all()
    assert db_session.get(Document, document.id).reread == "pending"  # type: ignore[union-attr]
    events = db_session.scalars(
        select(Outbox).where(Outbox.event_type == "document.uploaded.v1")
    ).all()
    assert [e.payload["document_id"] for e in events] == [str(document.id)]


def test_isolation_another_users_document_is_not_found(
    client: TestClient, db_session: Session
) -> None:
    _, _, document, _ = worked(db_session)
    _, other = signed_in(db_session)

    response = client.post(f"/v1/documents/{document.id}/reextract-outline", headers=other)

    assert response.status_code == 404
    assert db_session.get(Document, document.id).status == "indexed"  # type: ignore[union-attr]
    assert db_session.scalar(select(func.count()).select_from(Outbox)) == 0


def test_a_document_not_read_yet_is_refused(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    document = document_in(db_session, user, subject_of(db_session, user), status="uploaded")

    response = client.post(f"/v1/documents/{document.id}/reextract-outline", headers=headers)

    assert response.status_code == 409 and response.json()["detail"] == "not_indexed"


def test_asking_again_within_five_minutes_is_limited(
    client: TestClient, db_session: Session
) -> None:
    _, headers, document, _ = worked(db_session)
    url = f"/v1/documents/{document.id}/reextract-outline"
    assert client.post(url, headers=headers).status_code == 202

    again = client.post(url, headers=headers)

    assert again.status_code == 429


def test_a_reading_that_fails_keeps_the_document_and_its_outline(
    client: TestClient, db_session: Session
) -> None:
    user, headers, document, before = worked(db_session)
    assert (
        client.post(f"/v1/documents/{document.id}/reextract-outline", headers=headers).status_code
        == 202
    )

    on_document_failed(db_session, failed_event(document))
    db_session.flush()

    current = db_session.get(Document, document.id)
    assert current is not None and current.status == "indexed" and current.failure_reason is None
    assert current.toc_key is not None and current.reread == "failed"
    assert set(rows(db_session, user, document)) == set(before)  # the old outline, untouched
    outline = client.get(f"/v1/subjects/{document.subject_id}/outline", headers=headers).json()
    assert outline["reread"] == "failed" and outline["reason"] is None and outline["sections"]


def test_a_failure_without_a_reread_still_fails_the_document(db_session: Session) -> None:
    _, _, document, _ = worked(db_session)

    on_document_failed(db_session, failed_event(document))
    db_session.flush()

    current = db_session.get(Document, document.id)
    assert current is not None and current.status == "failed" and current.reread is None


def test_a_good_answer_clears_the_mark_and_a_failed_one_can_be_asked_again(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user, _, document, _ = worked(db_session)
    service = OutlineService(db_session, user.id)
    service.request_reextract(document.id)
    on_document_failed(db_session, failed_event(document))
    service.request_reextract(document.id)  # a failed reading can be asked for again
    OnDocumentIndexed(fake_storage)(db_session, answer(fake_storage, document))
    db_session.flush()

    current = db_session.get(Document, document.id)
    assert current is not None and current.reread is None and current.status == "indexed"


def test_an_unverified_email_is_refused(
    client: TestClient, db_session: Session, unverified_user: User
) -> None:

    token, _ = AuthSessionRepository(db_session).create(unverified_user.id, datetime.now(UTC))
    db_session.flush()

    response = client.post(
        f"/v1/documents/{uuid.uuid4()}/reextract-outline",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403 and response.json() == {"detail": "email_not_verified"}
    assert client.post(f"/v1/documents/{uuid.uuid4()}/reextract-outline").status_code == 401


def test_a_card_stays_under_its_chapter_when_a_section_is_added_above_it(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user, _ = signed_in(db_session)
    document = document_in(db_session, user, subject_of(db_session, user), pages=50)
    old = [
        NewSection("Chương 1. A", None, 1, 20, 20, "page", "heading"),
        NewSection("Chương 2. B", None, 21, 40, 20, "page", "heading"),
        NewSection("1. Bài tập", 1, 21, 40, 20, "page", "heading"),
    ]
    by_title = with_outline(db_session, user, document, old)
    exercise = by_title["1. Bài tập"]
    unit = make_unit(db_session, user, subject_of_id(exercise), status="canonical")  # pyright: ignore[reportArgumentType]
    link = UnitSection(subject_id=exercise.subject_id, unit_id=unit.id, section_id=exercise.id)
    link.user_id = user.id
    db_session.add(link)
    db_session.flush()
    new = {
        "unit": "page",
        "nodes": [
            node("Chương 1. A", None, 1, 20),
            node("1. Bài tập", 0, 1, 20),
            node("Chương 2. B", None, 21, 40),
            node("1. Bài tập", 2, 21, 40),
        ],
    }
    OutlineService(db_session, user.id).request_reextract(document.id)
    OnDocumentIndexed(fake_storage)(db_session, answer(fake_storage, document, new))
    db_session.flush()

    kept = db_session.get(DocSection, exercise.id)
    chapter2 = rows(db_session, user, document)["Chương 2. B"]
    assert kept is not None and kept.parent_id == chapter2.id
    assert db_session.scalar(select(func.count()).select_from(UnitSection)) == 1


def test_a_section_under_a_vanished_garbage_parent_moves_to_its_new_parent(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    # QA 05/11. Red when: an old "2.4.7" hung on by a card sits (excluded) under a stray ")" that
    # stays too, beside the new "2.4.7": the count grows and the learner sees ")" "Không thi".
    user, _ = signed_in(db_session)
    document = document_in(db_session, user, subject_of(db_session, user), pages=50)
    old = [
        NewSection("2. Quy luật", None, 1, 30, 30, "page", "heading"),
        NewSection("2.4. Thông dụng", 0, 1, 20, 20, "page", "heading"),
        NewSection(")", 0, 21, 30, 10, "page", "heading"),
        NewSection("2.4.7. Các định lí giới hạn", 2, 21, 30, 10, "page", "heading"),
    ]
    by_title = with_outline(db_session, user, document, old)
    limit = by_title["2.4.7. Các định lí giới hạn"]
    unit = make_unit(db_session, user, subject_of_id(limit), status="canonical")  # pyright: ignore[reportArgumentType]
    link = UnitSection(subject_id=limit.subject_id, unit_id=unit.id, section_id=limit.id)
    link.user_id = user.id
    db_session.add(link)
    db_session.flush()
    body = {
        "unit": "page",
        "nodes": [
            node("2. Quy luật", None, 1, 30),
            node("2.4. Thông dụng", 0, 1, 30),
            node("2.4.7. Các định lí giới hạn", 1, 21, 30),
        ],
    }

    OutlineService(db_session, user.id).request_reextract(document.id)
    OnDocumentIndexed(fake_storage)(db_session, answer(fake_storage, document, body))
    db_session.flush()

    after = rows(db_session, user, document)
    assert ")" not in after and len(after) == 3
    kept = after["2.4.7. Các định lí giới hạn"]
    assert kept.id == limit.id and not kept.excluded  # the card stays on the same row
    assert kept.parent_id == after["2.4. Thông dụng"].id
