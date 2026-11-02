"""T7.12d (US-02b AC14): `GET /v1/subjects/{id}/units/by-section` lists a subject's draft and
canonical cards grouped by outline section; cards with no section form a group of their own."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import UnitSection, User
from v2_rows import make_document, make_section, make_subject, make_unit


def _link(db: Session, user: User, unit: Any, section: Any) -> None:
    db.add(
        UnitSection(
            user_id=user.id, subject_id=unit.subject_id, unit_id=unit.id, section_id=section.id
        )
    )
    db.flush()


def _world(db: Session) -> tuple[User, dict[str, str], Any, dict[str, Any]]:
    user, headers = signed_in(db)
    subject = make_subject(db, user)
    doc = make_document(db, user, subject)
    s1 = make_section(db, user, doc, ord=0, title="Chương 1")
    s2 = make_section(db, user, doc, ord=1, title="Chương 2")
    a = make_unit(db, user, subject, title="A", status="canonical")
    b = make_unit(db, user, subject, title="B", status="draft")
    both = make_unit(db, user, subject, title="Cả hai", status="canonical")
    make_unit(db, user, subject, title="Lẻ", status="draft")
    gone = make_unit(db, user, subject, title="Bỏ", status="retired")
    _link(db, user, a, s1)
    _link(db, user, b, s2)
    _link(db, user, both, s1)
    _link(db, user, both, s2)
    _link(db, user, gone, s1)
    db.commit()
    return user, headers, subject, {"s1": s1, "s2": s2}


def _titles(group: dict[str, Any]) -> list[str]:
    return sorted(u["title"] for u in group["units"])


def test_ac14_groups_by_section_with_ungrouped_last(client: TestClient, db_session: Session):
    _, headers, subject, secs = _world(db_session)
    r = client.get(f"/v1/subjects/{subject.id}/units/by-section", headers=headers)
    assert r.status_code == 200
    groups = r.json()["groups"]
    assert [g["section_id"] for g in groups] == [str(secs["s1"].id), str(secs["s2"].id), None]
    assert [g["section_title"] for g in groups] == ["Chương 1", "Chương 2", None]
    assert _titles(groups[0]) == ["A", "Cả hai"]  # retired card left out
    assert _titles(groups[1]) == ["B", "Cả hai"]
    assert _titles(groups[2]) == ["Lẻ"]
    assert {"id", "title", "content", "kind", "status"} <= set(groups[0]["units"][0])


def test_ac14_two_users_never_see_each_other(client: TestClient, db_session: Session):
    _, headers_a, subject_a, _ = _world(db_session)
    _, headers_b, subject_b, _ = _world(db_session)
    assert (
        client.get(f"/v1/subjects/{subject_a.id}/units/by-section", headers=headers_b).status_code
        == 404
    )
    mine = client.get(f"/v1/subjects/{subject_b.id}/units/by-section", headers=headers_b).json()
    ids = {u["id"] for g in mine["groups"] for u in g["units"]}
    theirs = client.get(f"/v1/subjects/{subject_a.id}/units/by-section", headers=headers_a).json()
    assert ids.isdisjoint({u["id"] for g in theirs["groups"] for u in g["units"]})


def test_ac14_unverified_is_403(client: TestClient, db_session: Session):
    user, headers = signed_in(db_session, verified=False)
    subject = make_subject(db_session, user)
    db_session.commit()
    r = client.get(f"/v1/subjects/{subject.id}/units/by-section", headers=headers)
    assert r.status_code == 403


def test_ac14_empty_subject_has_no_groups(client: TestClient, db_session: Session):
    user, headers = signed_in(db_session)
    subject = make_subject(db_session, user)
    db_session.commit()
    r = client.get(f"/v1/subjects/{subject.id}/units/by-section", headers=headers)
    assert r.json() == {"groups": []}
