"""SESSION-END: a subject with no outline (no textbook with sections) cannot start a study session.
The gate is in core-api, not only on the screen (a stale link or a direct call is refused too)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from session_helpers import indexed_document, subject_of
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.config import get_settings
from fake_storage import FakeStorage
from v2_rows import make_section

pytestmark = pytest.mark.usefixtures("fake_storage")


@pytest.fixture(autouse=True)
def enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def test_no_textbook_no_draft(client: TestClient, db_session: Session) -> None:
    # Red when: a subject without any outline can open a study session.
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    response = client.post(f"/v1/subjects/{subject.id}/submission-drafts", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "no_syllabus"


def test_textbook_without_sections_no_draft(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Red when: a textbook still being read (no sections yet) counts as an outline.
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    book = indexed_document(db_session, fake_storage, user, subject)
    book.role = "textbook"
    db_session.flush()
    response = client.post(f"/v1/subjects/{subject.id}/submission-drafts", headers=headers)
    assert response.status_code == 409


def test_auxiliary_file_sections_are_not_an_outline(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Red when: sections of a non-textbook file open the gate (progress is the textbook's).
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    extra = indexed_document(db_session, fake_storage, user, subject)
    make_section(db_session, user, extra, title="Chương 1")
    response = client.post(f"/v1/subjects/{subject.id}/submission-drafts", headers=headers)
    assert response.status_code == 409


def test_textbook_with_sections_opens_the_session(
    client: TestClient, db_session: Session, fake_storage: FakeStorage
) -> None:
    # Red when: the gate also blocks a subject that has its outline.
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    book = indexed_document(db_session, fake_storage, user, subject)
    book.role = "textbook"
    make_section(db_session, user, book, title="Chương 1")
    response = client.post(f"/v1/subjects/{subject.id}/submission-drafts", headers=headers)
    assert response.status_code == 201


def test_unknown_subject_is_still_404(client: TestClient, db_session: Session) -> None:
    import uuid

    _, headers = signed_in(db_session)
    response = client.post(f"/v1/subjects/{uuid.uuid4()}/submission-drafts", headers=headers)
    assert response.status_code == 404
