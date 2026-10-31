"""T7.4: the main textbook of a subject and `PATCH /v1/documents/{id}` (US-01 AC5, AC7).

One textbook per subject. Replacing it never deletes: the old one becomes auxiliary with its
outline, links and covered pages; when cards are linked to it the learner confirms first.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from outline_rows import document_in, subject_of, with_outline
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import DocSection, Document, UnitSection
from core_api.repositories.doc_section import DocSectionRepository
from v2_rows import make_unit

pytestmark = pytest.mark.usefixtures("fake_storage")


def put(
    client: TestClient,
    headers: dict[str, str],
    subject_id: uuid.UUID,
    document_id: Any,
    **extra: Any,
) -> Any:
    return client.put(
        f"/v1/subjects/{subject_id}/textbook",
        json={"document_id": str(document_id), **extra},
        headers=headers,
    )


def role_of(session: Session, document: Document) -> str:
    session.refresh(document)
    return document.role


class Subject:
    def __init__(self, id: uuid.UUID) -> None:
        self.id = id


def link_card(session: Session, user: Any, section: DocSection, status: str = "canonical") -> None:
    unit = make_unit(session, user, Subject(section.subject_id), status=status)  # pyright: ignore[reportArgumentType]
    link = UnitSection(subject_id=section.subject_id, unit_id=unit.id, section_id=section.id)
    link.user_id = user.id
    session.add(link)
    session.flush()


# --- PUT textbook ---------------------------------------------------------------------------


def test_us01_ac5_the_first_textbook_is_set(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = document_in(db_session, user, subject, role="auxiliary")
    with_outline(db_session, user, document)

    response = put(client, headers, subject.id, document.id)

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["id"] == str(document.id) and body["reason"] is None
    assert [s["title"] for s in body["sections"]] == ["Chương 1", "Chương 2"]
    assert role_of(db_session, document) == "textbook"


def test_us01_ac5_setting_the_current_textbook_again_changes_nothing(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = document_in(db_session, user, subject)
    assert put(client, headers, subject.id, document.id).status_code == 200
    assert role_of(db_session, document) == "textbook"


def test_us01_ac5_changing_the_textbook_keeps_the_old_one_as_auxiliary(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    old = document_in(db_session, user, subject, "Cũ")
    with_outline(db_session, user, old)
    new = document_in(db_session, user, subject, "Mới", role="auxiliary")

    response = put(client, headers, subject.id, new.id)

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["short_name"] == "Mới"
    assert (body["reason"], body["sections"]) == ("no_outline", [])
    assert (role_of(db_session, old), role_of(db_session, new)) == ("auxiliary", "textbook")
    # nothing of the old textbook was deleted
    assert len(DocSectionRepository(db_session, user.id).of_document(old.id)) == 4


def test_us01_ac5_cards_linked_to_the_textbook_need_the_learners_confirmation(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    old = document_in(db_session, user, subject, "Cũ")
    sections = with_outline(db_session, user, old)
    link_card(db_session, user, sections["1.1"])
    link_card(db_session, user, sections["1.2"])
    new = document_in(db_session, user, subject, "Mới", role="auxiliary")

    refused = put(client, headers, subject.id, new.id)

    assert refused.status_code == 409
    assert refused.json() == {"detail": "textbook_has_cards", "cards": 2}
    assert (role_of(db_session, old), role_of(db_session, new)) == ("textbook", "auxiliary")

    confirmed = put(client, headers, subject.id, new.id, confirm=True)

    assert confirmed.status_code == 200
    assert (role_of(db_session, old), role_of(db_session, new)) == ("auxiliary", "textbook")
    # the cards keep their sections, and the old outline stays on the old document
    assert db_session.scalar(select(func.count()).select_from(UnitSection)) == 2
    assert len(DocSectionRepository(db_session, user.id).of_document(old.id)) == 4


def test_us01_ac5_a_draft_or_retired_card_does_not_need_confirmation(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    old = document_in(db_session, user, subject, "Cũ")
    sections = with_outline(db_session, user, old)
    link_card(db_session, user, sections["1.1"], status="draft")
    link_card(db_session, user, sections["1.2"], status="retired")
    new = document_in(db_session, user, subject, "Mới", role="auxiliary")
    assert put(client, headers, subject.id, new.id).status_code == 200


@pytest.mark.parametrize("status", ["pending", "rejected", "failed"])
def test_us01_ac5_a_document_not_read_cannot_be_the_textbook(
    client: TestClient, db_session: Session, status: str
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    old = document_in(db_session, user, subject, "Cũ")
    new = document_in(db_session, user, subject, "Mới", role="auxiliary", status=status)
    response = put(client, headers, subject.id, new.id)
    assert (response.status_code, response.json()["detail"]) == (409, "document_not_ready")
    assert role_of(db_session, old) == "textbook"


def test_us01_ac5_an_uploaded_document_can_be_the_textbook_while_it_is_read(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    new = document_in(db_session, user, subject, role="auxiliary", status="uploaded")
    body = put(client, headers, subject.id, new.id).json()
    assert body["reason"] == "not_indexed"


def test_isolation_the_textbook_must_be_of_that_subject_and_user(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    elsewhere = document_in(db_session, user, subject_of(db_session, user, "Toán"), "Toán")
    stranger, _ = signed_in(db_session)
    theirs = document_in(db_session, stranger, subject_of(db_session, stranger), "Của họ")
    for document_id in (elsewhere.id, theirs.id, uuid.uuid4()):
        response = put(client, headers, subject.id, document_id)
        assert (response.status_code, response.json()["detail"]) == (404, "document_not_found")
    assert role_of(db_session, elsewhere) == "textbook"
    assert role_of(db_session, theirs) == "textbook"


def test_isolation_another_users_subject_is_not_found(
    client: TestClient, db_session: Session
) -> None:
    user, _ = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = document_in(db_session, user, subject, role="auxiliary")
    _, other = signed_in(db_session)
    response = put(client, other, subject.id, document.id)
    assert (response.status_code, response.json()["detail"]) == (404, "subject_not_found")
    assert role_of(db_session, document) == "auxiliary"


def test_the_body_takes_a_document_id_and_a_confirm_flag_only(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = document_in(db_session, user, subject, role="auxiliary")
    for body in ({}, {"document_id": "x"}, {"document_id": str(document.id), "role": "textbook"}):
        response = client.put(f"/v1/subjects/{subject.id}/textbook", json=body, headers=headers)
        assert response.status_code == 422
    response = put(client, headers, subject.id, document.id, confirm="yes")
    assert response.status_code == 422


# --- PATCH document -------------------------------------------------------------------------


def patch_doc(client: TestClient, headers: dict[str, str], document: Document, **body: Any) -> Any:
    return client.patch(f"/v1/documents/{document.id}", json=body, headers=headers)


def test_us01_ac7_a_short_name_can_be_edited(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    document = document_in(db_session, user, subject_of(db_session, user), "Giáo trình")

    response = patch_doc(client, headers, document, short_name="  Mạng máy tính  ")

    assert response.status_code == 200
    assert (response.json()["short_name"], response.json()["role"]) == ("Mạng máy tính", "textbook")
    db_session.refresh(document)
    assert document.short_name == "Mạng máy tính"


def test_us01_ac7_a_name_taken_in_the_subject_is_refused(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document_in(db_session, user, subject, "Slide 1", role="auxiliary")
    document = document_in(db_session, user, subject, "Slide 2", role="auxiliary")
    response = patch_doc(client, headers, document, short_name="slide 1")
    assert (response.status_code, response.json()["detail"]) == (409, "short_name_taken")
    # the same name in another subject, or the document's own name, is fine
    other = document_in(db_session, user, subject_of(db_session, user, "Toán"), "Slide 1")
    assert patch_doc(client, headers, other, short_name="Slide 1").status_code == 200
    assert patch_doc(client, headers, document, short_name="Slide 2").status_code == 200


@pytest.mark.parametrize("name", ["", "   ", "​​", "a\u0000b", "a\nb", "x" * 256])
def test_us01_ac7_an_invalid_name_is_refused(
    client: TestClient, db_session: Session, name: str
) -> None:
    user, headers = signed_in(db_session)
    document = document_in(db_session, user, subject_of(db_session, user), "Giáo trình")
    assert patch_doc(client, headers, document, short_name=name).status_code == 422
    db_session.refresh(document)
    assert document.short_name == "Giáo trình"


def test_us01_ac5_a_second_textbook_by_role_change_is_refused(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    textbook = document_in(db_session, user, subject, "Giáo trình")
    other = document_in(db_session, user, subject, "Slide", role="auxiliary")

    response = patch_doc(client, headers, other, role="textbook")

    assert (response.status_code, response.json()["detail"]) == (409, "textbook_exists")
    assert (role_of(db_session, textbook), role_of(db_session, other)) == ("textbook", "auxiliary")
    # demoting the textbook frees the place
    assert (
        patch_doc(client, headers, textbook, role="question_bank").json()["role"] == "question_bank"
    )
    assert patch_doc(client, headers, other, role="textbook").json()["role"] == "textbook"


def test_a_role_must_be_one_of_the_three(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    document = document_in(db_session, user, subject_of(db_session, user))
    assert patch_doc(client, headers, document, role="admin").status_code == 422
    assert patch_doc(client, headers, document, status="indexed").status_code == 422
    assert patch_doc(client, headers, document).status_code == 422


def test_isolation_another_users_document_is_not_found(
    client: TestClient, db_session: Session
) -> None:
    user, _ = signed_in(db_session)
    document = document_in(db_session, user, subject_of(db_session, user), "Giáo trình")
    _, other = signed_in(db_session)
    response = patch_doc(client, other, document, short_name="Hack")
    assert (response.status_code, response.json()["detail"]) == (404, "document_not_found")
    db_session.refresh(document)
    assert document.short_name == "Giáo trình"


def test_the_document_answer_carries_its_role(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    document = document_in(db_session, user, subject_of(db_session, user), role="question_bank")
    response = client.get(f"/v1/documents/{document.id}", headers=headers)
    assert response.json()["role"] == "question_bank"
