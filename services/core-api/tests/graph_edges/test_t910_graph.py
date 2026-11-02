"""T9.10 (US-19 AC3, AC4): `GET /v1/subjects/{id}/graph` is the data of the graph screen: the
subject's canonical cards (with their anchors), the ACTIVE edges between them with their evidence,
the outline sections, at most 300 cards, one user only."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import (
    Anchor,
    KnowledgeUnit,
    QuestionUnit,
    Subject,
    UnitEdge,
    UnitSection,
    User,
)
from v2_rows import RUN, make_document, make_question, make_section, make_subject, make_unit


def _card(
    db: Session, user: User, subject: Subject, title: str = "Thẻ", **kw: Any
) -> KnowledgeUnit:
    unit = make_unit(db, user, subject, title=title, status="canonical", **kw)
    db.add(
        Anchor(
            user_id=user.id,
            unit_id=unit.id,
            source="notes",
            quote_text=f"Trích {title}",
            run_id=RUN,
        )
    )
    db.flush()
    return unit


def _edge(
    db: Session, user: User, subject: Subject, src: KnowledgeUnit, dst: KnowledgeUnit, **kw: Any
) -> UnitEdge:
    values: dict[str, Any] = {
        "user_id": user.id,
        "subject_id": subject.id,
        "src_unit_id": src.id,
        "dst_unit_id": dst.id,
        "kind": "prerequisite",
        "origin": "ai",
        "status": "active",
        "evidence": [{"unit_id": str(src.id), "quote": "câu trích"}],
    }
    values.update(kw)
    row = UnitEdge(**values)
    db.add(row)
    db.flush()
    return row


def _link(db: Session, user: User, unit: KnowledgeUnit, section: Any) -> None:
    db.add(
        UnitSection(
            user_id=user.id, subject_id=unit.subject_id, unit_id=unit.id, section_id=section.id
        )
    )
    db.flush()


def _get(client: TestClient, headers: dict[str, str], subject: Subject, **params: str) -> Any:
    return client.get(f"/v1/subjects/{subject.id}/graph", headers=headers, params=params)


def test_ac3_cards_edges_sections_and_evidence(client: TestClient, db_session: Session):
    user, headers = signed_in(db_session)
    subject = make_subject(db_session, user)
    doc = make_document(db_session, user, subject)
    s1 = make_section(db_session, user, doc, ord=0, title="Chương 1")
    s11 = make_section(db_session, user, doc, ord=1, title="1.1", parent_id=s1.id)
    a, b = _card(db_session, user, subject, "A"), _card(db_session, user, subject, "B")
    _link(db_session, user, a, s11)
    question = make_question(db_session, user, subject, prompt="Vì sao A?")
    db_session.add(
        QuestionUnit(user_id=user.id, subject_id=subject.id, question_id=question.id, unit_id=a.id)
    )
    edge = _edge(db_session, user, subject, a, b)
    db_session.commit()
    body = _get(client, headers, subject).json()
    assert body["hidden"] == 0 and body["truncated"] is False
    assert [s["title"] for s in body["sections"]] == ["Chương 1", "1.1"]
    assert body["sections"][1]["parent_id"] == str(s1.id)
    cards = {c["title"]: c for c in body["cards"]}
    assert cards["A"]["section_id"] == str(s11.id) and cards["B"]["section_id"] is None
    assert cards["A"]["anchors"][0]["quote"] == "Trích A"
    assert cards["A"]["needed_by"] == ["Vì sao A?"]
    [e] = body["edges"]
    assert (e["id"], e["kind"]) == (str(edge.id), "prerequisite")
    assert (e["from_id"], e["to_id"]) == (str(a.id), str(b.id))
    assert e["evidence"] == [{"unit_id": str(a.id), "quote": "câu trích"}]


def test_ac3_edge_touching_a_non_canonical_card_is_not_returned(
    client: TestClient, db_session: Session
):
    # T9.9 review F1: filtered at read time, so a draft or retired card never leaks through an edge.
    user, headers = signed_in(db_session)
    subject = make_subject(db_session, user)
    a, b = _card(db_session, user, subject, "A"), _card(db_session, user, subject, "B")
    draft = make_unit(db_session, user, subject, title="Nháp", status="draft")
    gone = _card(db_session, user, subject, "Bỏ")
    _edge(db_session, user, subject, a, b)
    _edge(db_session, user, subject, a, draft)
    _edge(db_session, user, subject, gone, b)
    gone.status, gone.retired_at = "retired", datetime.now(UTC)
    db_session.commit()
    body = _get(client, headers, subject).json()
    assert sorted(c["title"] for c in body["cards"]) == ["A", "B"]
    assert [(e["from_id"], e["to_id"]) for e in body["edges"]] == [(str(a.id), str(b.id))]


def test_ac3_only_active_edges(client: TestClient, db_session: Session):
    user, headers = signed_in(db_session)
    subject = make_subject(db_session, user)
    a, b = _card(db_session, user, subject, "A"), _card(db_session, user, subject, "B")
    _edge(db_session, user, subject, a, b, kind="part_of", status="rejected")
    _edge(db_session, user, subject, a, b, kind="applies_to", status="inactive")
    db_session.commit()
    assert _get(client, headers, subject).json()["edges"] == []


def test_ac3_two_users_never_see_each_other(client: TestClient, db_session: Session):
    user_a, _ = signed_in(db_session)
    user_b, headers_b = signed_in(db_session)
    sub_a, sub_b = make_subject(db_session, user_a), make_subject(db_session, user_b)
    _card(db_session, user_a, sub_a, "Của A")
    _card(db_session, user_b, sub_b, "Của B")
    db_session.commit()
    assert _get(client, headers_b, sub_a).status_code == 404
    assert [c["title"] for c in _get(client, headers_b, sub_b).json()["cards"]] == ["Của B"]


def test_ac3_unverified_is_403(client: TestClient, db_session: Session):
    user, headers = signed_in(db_session, verified=False)
    subject = make_subject(db_session, user)
    db_session.commit()
    assert _get(client, headers, subject).status_code == 403


def test_ac3_at_most_300_cards_with_a_neutral_flag(client: TestClient, db_session: Session):
    user, headers = signed_in(db_session)
    subject = make_subject(db_session, user)
    db_session.add_all(
        KnowledgeUnit(
            user_id=user.id,
            subject_id=subject.id,
            title=f"T{i}",
            summary="s",
            kind="concept",
            status="canonical",
            run_id=RUN,
        )
        for i in range(305)
    )
    db_session.commit()
    body = _get(client, headers, subject).json()
    assert len(body["cards"]) == 300 and body["hidden"] == 5 and body["truncated"] is True


def test_ac3_section_filter_takes_the_subtree(client: TestClient, db_session: Session):
    user, headers = signed_in(db_session)
    subject = make_subject(db_session, user)
    doc = make_document(db_session, user, subject)
    s1 = make_section(db_session, user, doc, ord=0, title="Chương 1")
    s11 = make_section(db_session, user, doc, ord=1, title="1.1", parent_id=s1.id)
    s2 = make_section(db_session, user, doc, ord=2, title="Chương 2")
    a, b, c = (_card(db_session, user, subject, n) for n in "ABC")
    _link(db_session, user, a, s1)
    _link(db_session, user, b, s11)
    _link(db_session, user, c, s2)
    _edge(db_session, user, subject, a, b)
    _edge(db_session, user, subject, b, c)
    db_session.commit()
    body = _get(client, headers, subject, section_id=str(s1.id)).json()
    assert sorted(x["title"] for x in body["cards"]) == ["A", "B"]
    assert [(e["from_id"], e["to_id"]) for e in body["edges"]] == [(str(a.id), str(b.id))]
    assert body["truncated"] is False
    # the picker still lists every section that holds a card
    assert [x["title"] for x in body["sections"]] == ["Chương 1", "1.1", "Chương 2"]


def test_ac3_section_of_another_user_or_unknown_is_404(client: TestClient, db_session: Session):
    user_a, headers_a = signed_in(db_session)
    user_b, _ = signed_in(db_session)
    sub_a, sub_b = make_subject(db_session, user_a), make_subject(db_session, user_b)
    foreign = make_section(db_session, user_b, make_document(db_session, user_b, sub_b))
    db_session.commit()
    assert _get(client, headers_a, sub_a, section_id=str(foreign.id)).status_code == 404
    assert _get(client, headers_a, sub_a, section_id=str(uuid.uuid4())).status_code == 404
