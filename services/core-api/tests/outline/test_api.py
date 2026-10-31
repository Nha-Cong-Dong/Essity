"""T7.4 API: `GET /v1/subjects/{id}/outline`, `PATCH /v1/sections/{id}` (US-13 AC4-AC6, US-01 AC5).

A user reads and edits only their own outline; another user's, or another subject's, is a 404 (or
an empty outline), the same as one that does not exist.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from outline_rows import PAGES, document_in, subject_of, with_outline
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import DocSection, Document, User

pytestmark = pytest.mark.usefixtures("fake_storage")


def world(session: Session) -> tuple[User, dict[str, str], Any, Document, dict[str, DocSection]]:
    user, headers = signed_in(session)
    subject = subject_of(session, user)
    document = document_in(session, user, subject)
    return user, headers, subject, document, with_outline(session, user, document)


def get(client: TestClient, headers: dict[str, str], subject_id: uuid.UUID) -> dict[str, Any]:
    response = client.get(f"/v1/subjects/{subject_id}/outline", headers=headers)
    assert response.status_code == 200
    return response.json()


def flat(tree: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for item in tree:
        found[item["title"]] = item
        found.update(flat(item["children"]))
    return found


def patch(client: TestClient, headers: dict[str, str], section: DocSection, **body: Any) -> Any:
    return client.patch(f"/v1/sections/{section.id}", json=body, headers=headers)


# --- GET -----------------------------------------------------------------------------------


def test_us13_ac1_the_tree_has_weight_unit_source_and_state(
    client: TestClient, db_session: Session
) -> None:
    _, headers, subject, document, _ = world(db_session)

    body = get(client, headers, subject.id)

    assert body["reason"] is None and body["temporary"] is False
    assert body["document"] == {
        "id": str(document.id),
        "short_name": "Giáo trình",
        "page_count": 40,
    }
    assert [s["title"] for s in body["sections"]] == ["Chương 1", "Chương 2"]
    chapter = body["sections"][0]
    assert [c["title"] for c in chapter["children"]] == ["1.1", "1.2"]
    assert (chapter["weight"], chapter["unit"], chapter["source"]) == (20, "page", "bookmark")
    assert (chapter["first_page"], chapter["last_page"]) == (1, 20)
    assert chapter["progress"] == 0 and chapter["studied"] is False
    assert chapter["excluded"] is False and chapter["excluded_effective"] is False
    assert body["progress"] == 0


def test_us13_ac8_no_textbook_says_why(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    body = get(client, headers, subject.id)
    assert (body["document"], body["reason"], body["sections"]) == (None, "no_textbook", [])

    document_in(db_session, user, subject, role="auxiliary")
    assert get(client, headers, subject.id)["reason"] == "no_textbook"


def test_us13_ac9_textbook_still_being_read_says_so(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document_in(db_session, user, subject, status="uploaded")
    assert get(client, headers, subject.id)["reason"] == "not_indexed"


def test_us13_ac9_indexed_textbook_without_an_outline_says_so(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document_in(db_session, user, subject)
    body = get(client, headers, subject.id)
    assert (body["reason"], body["sections"]) == ("no_outline", [])


def test_us13_ac2_a_chunk10_tree_is_marked_temporary(
    client: TestClient, db_session: Session
) -> None:
    from core_api.repositories.doc_section import NewSection

    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document = document_in(db_session, user, subject)
    with_outline(
        db_session, user, document, [NewSection("Pages 1-40", None, 1, 40, 40, "page", "chunk10")]
    )
    assert get(client, headers, subject.id)["temporary"] is True


def test_us13_ac4_a_failed_textbook_is_not_the_textbook(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject = subject_of(db_session, user)
    document_in(db_session, user, subject, status="failed")
    assert get(client, headers, subject.id)["document"] is None


def test_isolation_another_users_subject_is_not_found(
    client: TestClient, db_session: Session
) -> None:
    _, _, subject, _, _ = world(db_session)
    _, other = signed_in(db_session)
    response = client.get(f"/v1/subjects/{subject.id}/outline", headers=other)
    assert (response.status_code, response.json()["detail"]) == (404, "subject_not_found")


def test_isolation_a_subject_never_shows_another_subjects_textbook(
    client: TestClient, db_session: Session
) -> None:
    user, headers, _, _, _ = world(db_session)
    second = subject_of(db_session, user, "Toán")
    body = get(client, headers, second.id)
    assert (body["document"], body["reason"], body["sections"]) == (None, "no_textbook", [])


def test_an_unverified_user_reads_and_edits_nothing(
    client: TestClient, db_session: Session
) -> None:
    _, _, subject, _, sections = world(db_session)
    _, unverified = signed_in(db_session, verified=False)
    assert client.get(f"/v1/subjects/{subject.id}/outline", headers=unverified).status_code == 403
    assert patch(client, unverified, sections["1.1"], excluded=True).status_code == 403
    assert (
        client.put(
            f"/v1/subjects/{subject.id}/textbook",
            json={"document_id": str(uuid.uuid4())},
            headers=unverified,
        ).status_code
        == 403
    )


def test_a_deleted_subject_has_no_outline(client: TestClient, db_session: Session) -> None:
    from datetime import UTC, datetime

    _, headers, subject, _, sections = world(db_session)
    subject.deleted_at = datetime.now(UTC)
    db_session.flush()
    assert client.get(f"/v1/subjects/{subject.id}/outline", headers=headers).status_code == 404
    assert patch(client, headers, sections["1.1"], excluded=True).status_code == 404


# --- PATCH range -----------------------------------------------------------------------------


def test_us13_ac4_a_range_is_saved_as_the_learners(client: TestClient, db_session: Session) -> None:
    _, headers, subject, _, sections = world(db_session)

    response = patch(client, headers, sections["1.1"], first_page=2, last_page=6)

    assert response.status_code == 200
    items = flat(response.json()["sections"])
    assert (items["1.1"]["first_page"], items["1.1"]["last_page"]) == (2, 6)
    assert (items["1.1"]["source"], items["1.1"]["weight"]) == ("user", 5)
    # the parent weighs what is under it: 5 + 12
    assert items["Chương 1"]["weight"] == 17
    assert items["Chương 1"]["source"] == "bookmark"
    assert get(client, headers, subject.id)["sections"][0]["children"][0]["first_page"] == 2


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"first_page": 0, "last_page": 5}, "invalid_range"),
        ({"first_page": -3, "last_page": 5}, "invalid_range"),
        ({"first_page": 6, "last_page": 5}, "invalid_range"),
        ({"first_page": 3}, "invalid_range"),
        ({"last_page": 3}, "invalid_range"),
        ({"first_page": 1, "last_page": PAGES + 1}, "outside_document"),
        ({"first_page": 1, "last_page": 21}, "outside_parent"),
        ({"first_page": 0 + 21, "last_page": 22}, "outside_parent"),
        ({}, "nothing_to_change"),
    ],
)
def test_us13_ac4_a_range_that_breaks_a_rule_is_refused(
    client: TestClient, db_session: Session, body: dict[str, Any], code: str
) -> None:
    _, headers, subject, _, sections = world(db_session)
    response = client.patch(f"/v1/sections/{sections['1.1'].id}", json=body, headers=headers)
    assert (response.status_code, response.json()["detail"]) == (422, code)
    assert get(client, headers, subject.id)["sections"][0]["children"][0]["first_page"] == 1


def test_us13_ac4_a_parent_cannot_shrink_off_its_children(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _, _, sections = world(db_session)
    response = patch(client, headers, sections["Chương 1"], first_page=3, last_page=20)
    assert (response.status_code, response.json()["detail"]) == (422, "children_outside")
    assert (
        patch(client, headers, sections["Chương 1"], first_page=1, last_page=20).status_code == 200
    )


def test_us13_ac4_a_root_may_move_to_the_ends_of_the_document(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _, _, sections = world(db_session)
    assert (
        patch(client, headers, sections["Chương 2"], first_page=21, last_page=PAGES).status_code
        == 200
    )
    response = patch(client, headers, sections["Chương 2"], first_page=1, last_page=1)
    assert response.status_code == 200


def test_us13_ac4_a_section_without_pages_has_no_range_to_edit(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _, _, sections = world(db_session)
    sections["Chương 2"].first_page = sections["Chương 2"].last_page = None
    db_session.flush()
    response = patch(client, headers, sections["Chương 1"], first_page=1, last_page=20)
    assert (response.status_code, response.json()["detail"]) == (422, "invalid_range")
    assert patch(client, headers, sections["Chương 1"], excluded=True).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"first_page": "2", "last_page": 5},
        {"first_page": 2.5, "last_page": 5},
        {"first_page": True, "last_page": 5},
        {"excluded": "yes"},
        {"studied": 1},
        {"title": "x"},
        {"weight": 3},
        {"source": "user"},
    ],
)
def test_a_patch_with_other_fields_or_types_is_refused(
    client: TestClient, db_session: Session, body: dict[str, Any]
) -> None:
    _, headers, _, _, sections = world(db_session)
    response = client.patch(f"/v1/sections/{sections['1.1'].id}", json=body, headers=headers)
    assert response.status_code == 422


# --- PATCH excluded / studied ----------------------------------------------------------------


def test_us13_ac5_an_excluded_section_leaves_the_progress(
    client: TestClient, db_session: Session
) -> None:
    _, headers, subject, _, sections = world(db_session)
    patch(client, headers, sections["Chương 2"], studied=True)
    assert get(client, headers, subject.id)["progress"] == pytest.approx(0.5)

    response = patch(client, headers, sections["Chương 1"], excluded=True)

    body = response.json()
    items = flat(body["sections"])
    assert body["progress"] == pytest.approx(1.0)
    assert items["Chương 1"]["excluded"] is True
    assert items["1.1"]["excluded"] is False and items["1.1"]["excluded_effective"] is True
    assert items["Chương 1"]["source"] == "user"
    again = patch(client, headers, sections["Chương 1"], excluded=False).json()
    assert again["progress"] == pytest.approx(0.5)


def test_us13_ac5_studied_on_a_parent_marks_every_leaf_under_it(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _, _, sections = world(db_session)

    body = patch(client, headers, sections["Chương 1"], studied=True).json()

    items = flat(body["sections"])
    assert (items["1.1"]["studied"], items["1.2"]["studied"], items["Chương 1"]["studied"]) == (
        True,
        True,
        True,
    )
    assert items["Chương 2"]["studied"] is False
    assert body["progress"] == pytest.approx(0.5)
    # studied is state, not a change of outline
    assert items["1.1"]["source"] == "bookmark"

    body = patch(client, headers, sections["1.1"], studied=False).json()
    items = flat(body["sections"])
    assert items["1.1"]["studied"] is False and items["Chương 1"]["studied"] is False
    assert body["progress"] == pytest.approx(12 / 40)


def test_us13_ac6_a_partly_covered_section_counts_by_the_part(
    client: TestClient, db_session: Session
) -> None:
    _, headers, subject, _, sections = world(db_session)
    sections["1.2"].studied_weight = 6  # six of its twelve pages
    db_session.flush()

    body = get(client, headers, subject.id)

    items = flat(body["sections"])
    assert items["1.2"]["progress"] == pytest.approx(0.5) and items["1.2"]["studied"] is False
    assert items["Chương 1"]["progress"] == pytest.approx(6 / 20)
    assert body["progress"] == pytest.approx(6 / 40)


def test_us13_ac6_the_same_range_gives_the_same_state_whatever_the_cards(
    client: TestClient, db_session: Session
) -> None:
    # Studied is read from the covered weight alone: no card or question count enters it.
    _, headers, subject, _, sections = world(db_session)
    sections["1.1"].studied_weight = 8
    db_session.flush()
    assert flat(get(client, headers, subject.id)["sections"])["1.1"]["studied"] is True


def test_us13_ac6_an_edit_pulls_studied_weight_back_inside_the_weight(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _, _, sections = world(db_session)
    sections["1.1"].studied_weight = 99  # over its weight of 8, as a stale row could be
    sections["Chương 2"].studied_weight = 5
    db_session.flush()

    assert patch(client, headers, sections["Chương 2"], excluded=True).status_code == 200

    db_session.refresh(sections["1.1"])
    assert sections["1.1"].studied_weight == 8
    assert 0 <= sections["Chương 2"].studied_weight <= sections["Chương 2"].weight


def test_us13_ac6_editing_the_range_of_a_studied_section_keeps_it_studied(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _, _, sections = world(db_session)
    patch(client, headers, sections["1.1"], studied=True)

    items = flat(
        patch(client, headers, sections["1.1"], first_page=1, last_page=10).json()["sections"]
    )

    assert items["1.1"]["weight"] == 10 and items["1.1"]["studied"] is True
    # partly covered keeps what still fits
    sections["1.2"].studied_weight = 9
    db_session.flush()
    items = flat(
        patch(client, headers, sections["1.2"], first_page=11, last_page=14).json()["sections"]
    )
    assert items["1.2"]["weight"] == 4
    assert items["1.2"]["studied"] is True  # 9 covered of 12 became min(9, 4): all of the 4 pages


def test_us13_ac4_a_section_of_another_user_is_not_found(
    client: TestClient, db_session: Session
) -> None:
    _, _, _, _, sections = world(db_session)
    _, other = signed_in(db_session)
    for body in ({"excluded": True}, {"first_page": 1, "last_page": 2}, {"studied": True}):
        response = client.patch(f"/v1/sections/{sections['1.1'].id}", json=body, headers=other)
        assert (response.status_code, response.json()["detail"]) == (404, "section_not_found")
    assert (
        db_session.scalars(
            select(DocSection.excluded).where(DocSection.id == sections["1.1"].id)
        ).one()
        is False
    )


def test_an_unknown_section_is_not_found(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    response = client.patch(
        f"/v1/sections/{uuid.uuid4()}", json={"excluded": True}, headers=headers
    )
    assert (response.status_code, response.json()["detail"]) == (404, "section_not_found")
