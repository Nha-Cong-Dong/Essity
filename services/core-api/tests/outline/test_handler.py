"""T7.4 (US-13 AC1-AC4, AC9; US-01 AC6): `document.indexed.v1` stores the outline ai-service read.

The handler runs on the test session, as the consumer's claimed transaction would run it.
"""

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.clients.storage import StorageUnavailableError
from core_api.db.models import (
    DocSection,
    Document,
    KnowledgeUnit,
    Question,
    UnitSection,
    User,
)
from core_api.handlers.document_indexed import MAX_SECTIONS, OnDocumentIndexed, parse_outline
from core_api.messaging.envelope import DocumentIndexedEvent
from core_api.repositories.doc_section import DocSectionRepository
from core_api.services.outline import OutlineService
from documents.test_document_indexed import indexed_event, uploaded
from fake_storage import FakeStorage
from v2_rows import make_unit

PAGE_COUNT = 40
pytestmark = pytest.mark.usefixtures("fake_storage")


def node(title: str, parent: int | None, start: int, end: int, source: str = "bookmark") -> Any:
    return {
        "title": title,
        "parent": parent,
        "page_start": start,
        "page_end": end,
        "weight": end - start + 1,
        "source": source,
    }


GOOD = {
    "unit": "page",
    "nodes": [node("Chương 1", None, 1, 20), node("1.1", 0, 1, 8), node("Chương 2", None, 21, 40)],
}


def answer(
    storage: FakeStorage,
    document: Document,
    body: Any = GOOD,
    *,
    raw: bytes | None = None,
    user_id: uuid.UUID | None = None,
) -> DocumentIndexedEvent:
    """A `document.indexed.v1` for the document, with `outline.json` beside its derived files."""
    event = indexed_event(document, user_id, payload={"page_count": PAGE_COUNT})
    key = event.payload.toc_key.rsplit("/", 1)[0] + "/outline.json"
    storage.objects[key] = (raw if raw is not None else json.dumps(body).encode(), None)
    return event


def run(session: Session, storage: FakeStorage, event: DocumentIndexedEvent) -> None:
    OnDocumentIndexed(storage)(session, event)
    session.flush()


def titles(session: Session, user: User, document: Document) -> list[tuple[str, int | None, str]]:
    rows = DocSectionRepository(session, user.id).of_document(document.id)
    return [(r.title, r.first_page, r.source) for r in rows]


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(DocSection)) or 0


def test_us13_ac1_indexed_event_stores_the_tree(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)

    run(db_session, fake_storage, answer(fake_storage, document))

    rows = DocSectionRepository(db_session, user.id).of_document(document.id)
    assert [(r.title, r.first_page, r.last_page, r.weight, r.unit, r.source) for r in rows] == [
        ("Chương 1", 1, 20, 20, "page", "bookmark"),
        ("1.1", 1, 8, 8, "page", "bookmark"),
        ("Chương 2", 21, 40, 20, "page", "bookmark"),
    ]
    assert rows[1].parent_id == rows[0].id and rows[0].parent_id is None
    assert document.status == "indexed"
    assert all(r.subject_id == document.subject_id and r.user_id == user.id for r in rows)


def test_us13_ac4_the_same_event_twice_makes_no_duplicates(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    event = answer(fake_storage, document)

    run(db_session, fake_storage, event)
    run(db_session, fake_storage, event)

    assert count(db_session) == 3


def test_us13_ac4_a_new_run_replaces_an_untouched_outline(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    run(db_session, fake_storage, answer(fake_storage, document))

    other = {"unit": "page", "nodes": [node("Only", None, 1, 40, "chunk10")]}
    run(db_session, fake_storage, answer(fake_storage, document, other))

    assert titles(db_session, user, document) == [("Only", 1, "chunk10")]


@pytest.mark.parametrize("touch", ["range", "excluded", "studied"])
def test_us13_ac4_a_learners_work_is_not_overwritten(
    db_session: Session, fake_storage: FakeStorage, touch: str
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    run(db_session, fake_storage, answer(fake_storage, document))
    service = OutlineService(db_session, user.id)
    section = DocSectionRepository(db_session, user.id).of_document(document.id)[1]
    if touch == "range":
        service.edit_section(section.id, first_page=2, last_page=8)
    elif touch == "excluded":
        service.edit_section(section.id, excluded=True)
    else:
        service.edit_section(section.id, studied=True)
    before = titles(db_session, user, document)

    other = {"unit": "page", "nodes": [node("Other", None, 1, 40, "llm_toc")]}
    run(db_session, fake_storage, answer(fake_storage, document, other))

    assert titles(db_session, user, document) == before


def test_us13_ac4_linked_cards_keep_their_sections(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    run(db_session, fake_storage, answer(fake_storage, document))
    section = DocSectionRepository(db_session, user.id).of_document(document.id)[0]
    unit = make_unit(db_session, user, _Subject(section.subject_id), status="canonical")  # pyright: ignore[reportArgumentType]
    link = UnitSection(subject_id=section.subject_id, unit_id=unit.id, section_id=section.id)
    link.user_id = user.id
    db_session.add(link)
    db_session.flush()
    before = titles(db_session, user, document)

    other = {"unit": "page", "nodes": [node("Other", None, 1, 40, "llm_toc")]}
    run(db_session, fake_storage, answer(fake_storage, document, other))

    assert titles(db_session, user, document) == before
    assert db_session.scalar(select(func.count()).select_from(UnitSection)) == 1


class _Subject:
    """What `make_unit` reads of a subject: its id."""

    def __init__(self, id: uuid.UUID) -> None:
        self.id = id


def test_us13_ac9_chunk10_outline_is_stored_as_temporary(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    body = {"unit": "page", "nodes": [node("Pages 1-10", None, 1, 10, "chunk10")]}
    run(db_session, fake_storage, answer(fake_storage, document, body))
    assert titles(db_session, user, document) == [("Pages 1-10", 1, "chunk10")]


def test_us01_ac6_indexing_creates_no_unit_or_question(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    units = select(func.count()).select_from(KnowledgeUnit)
    questions = select(func.count()).select_from(Question)
    before = (db_session.scalar(units), db_session.scalar(questions))

    run(db_session, fake_storage, answer(fake_storage, document))

    assert (db_session.scalar(units), db_session.scalar(questions)) == before


def test_no_file_leaves_the_document_indexed_with_no_outline(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    event = indexed_event(document, payload={"page_count": PAGE_COUNT})

    run(db_session, fake_storage, event)

    assert document.status == "indexed" and count(db_session) == 0


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        json.dumps({"unit": "page", "nodes": []}).encode(),
        json.dumps({"unit": "page", "nodes": [node("x", None, 5, 4)]}).encode(),
        json.dumps({"unit": "page", "nodes": [node("x", None, 1, 41)]}).encode(),
        json.dumps({"unit": "page", "nodes": [node("x", 0, 1, 4)]}).encode(),
        json.dumps({"unit": "page", "nodes": [node("x", 1, 1, 4), node("y", None, 1, 4)]}).encode(),
        json.dumps(
            {"unit": "page", "nodes": [node("a", None, 1, 10), node("b", 0, 5, 12)]}
        ).encode(),
        json.dumps({"unit": "page", "nodes": [node("  ", None, 1, 4)]}).encode(),
        json.dumps({"unit": "page", "nodes": [node("a\u0000b", None, 1, 4)]}).encode(),
        json.dumps({"unit": "page", "nodes": [node("x", None, 1, 4, "user")]}).encode(),
        json.dumps({"unit": "foot", "nodes": [node("x", None, 1, 4)]}).encode(),
        json.dumps({"unit": "page", "nodes": [{**node("x", None, 1, 4), "extra": 1}]}).encode(),
    ],
)
def test_a_broken_outline_file_is_refused(body: bytes) -> None:
    assert parse_outline(body, PAGE_COUNT) is None


def test_too_many_sections_are_refused() -> None:
    nodes = [node(f"s{i}", None, 1, 1) for i in range(MAX_SECTIONS + 1)]
    assert parse_outline(json.dumps({"unit": "page", "nodes": nodes}).encode(), 5) is None


def test_a_broken_file_stores_nothing(db_session: Session, fake_storage: FakeStorage) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    run(db_session, fake_storage, answer(fake_storage, document, raw=b"{"))
    assert count(db_session) == 0 and document.status == "indexed"


def test_another_users_document_gets_no_outline_f2(
    db_session: Session, fake_storage: FakeStorage, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    document = uploaded(db_session, alice)
    run(db_session, fake_storage, answer(fake_storage, document, user_id=bob.id))
    assert count(db_session) == 0 and document.status == "uploaded"


def test_an_unconfirmed_document_gets_no_outline(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user, "pending")
    run(db_session, fake_storage, answer(fake_storage, document))
    assert count(db_session) == 0


def test_the_storage_not_answering_raises_for_a_retry(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    event = answer(fake_storage, document)
    fake_storage.down = True
    with pytest.raises(StorageUnavailableError):
        OnDocumentIndexed(fake_storage)(db_session, event)


def test_the_consumer_uses_the_outline_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    from core_api.messaging import consumer

    def from_settings(settings: object) -> FakeStorage:
        return FakeStorage()

    monkeypatch.setattr("core_api.clients.storage.S3Storage.from_settings", from_settings)
    assert isinstance(consumer.build_handlers()["document.indexed.v1"], OnDocumentIndexed)
