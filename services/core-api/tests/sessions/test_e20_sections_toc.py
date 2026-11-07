"""E-20: an empty toc.json goes to ai-service as the outline's doc_section headings."""

import json

import pytest
from fastapi.testclient import TestClient
from session_helpers import indexed_document, proposed, subject_of
from sqlalchemy.orm import Session
from test_create_session import post

from accounts import signed_in
from fake_ai_service import FakeAi
from fake_storage import FakeStorage
from v2_rows import make_section

pytestmark = pytest.mark.usefixtures("fake_storage", "fake_ai")


def test_e20_empty_toc_sends_the_outline_sections_with_pages(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    # Red when: an empty toc.json goes to ai-service as it is, so "mục 1.4" never resolves.
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject, pages=30, toc=[])
    root = make_section(
        db_session, user, document, ord=0, title="Chương 1", first_page=1, last_page=30
    )
    make_section(
        db_session,
        user,
        document,
        ord=0,
        title="1.4 Công thức Bayes",
        parent_id=root.id,
        first_page=17,
        last_page=26,
    )
    make_section(db_session, user, document, ord=1, title="Chưa có trang", parent_id=root.id)
    fake_ai.answer = proposed(document)

    post(client, headers, subject.id)

    [doc] = json.loads(fake_ai.requests[0].content)["documents"]
    assert doc["toc"] == [
        {"title": "Chương 1", "level": 0, "page": 1},
        {"title": "1.4 Công thức Bayes", "level": 1, "page": 17},
        {"title": "Chưa có trang", "level": 1, "page": None},
    ]


def test_e20_real_toc_is_kept_over_sections(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, fake_ai: FakeAi
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = indexed_document(db_session, fake_storage, user, subject, pages=10)
    make_section(db_session, user, document, title="Khác", first_page=1, last_page=5)
    fake_ai.answer = proposed(document)

    post(client, headers, subject.id)

    [doc] = json.loads(fake_ai.requests[0].content)["documents"]
    assert doc["toc"] == [{"title": "Chương 3", "level": 0, "page": 3}]
