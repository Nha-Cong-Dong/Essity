"""T8.2 (US-14 AC3-AC6): GET /v1/subjects/{id}/questions lists a subject's bank questions with
their readiness. Rows are written through the models; readiness is computed on every read, so a
card saved later flips the question with no extra step."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_question_banks_api import indexed_fields

from accounts import signed_in
from core_api.db.models import (
    DocSection,
    KnowledgeUnit,
    Question,
    QuestionSection,
    UnitSection,
    User,
)
from v2_rows import make_document, make_question, make_section, make_subject, make_type, make_unit

Headers = dict[str, str]


class Bench:
    def __init__(self, client: TestClient, session: Session, user: User, headers: Headers) -> None:
        self.client, self.session, self.user, self.headers = client, session, user, headers
        self.subject = make_subject(session, user)
        self.book = make_document(
            session, user, self.subject, sha="cd" * 32, role="textbook", **indexed_fields()
        )
        self.bank = make_document(
            session, user, self.subject, sha="ef" * 32, role="question_bank", **indexed_fields()
        )
        self.n = 0
        self.sections = 0

    def section(self, title: str, studied: bool = True, **kw: Any) -> DocSection:
        weight = kw.pop("weight", 2.0)
        kw.setdefault("ord", self.sections)
        self.sections += 1
        return make_section(
            self.session,
            self.user,
            self.book,
            title=title,
            weight=weight,
            studied_weight=weight if studied else 0.0,
            **kw,
        )

    def card(self, section: DocSection, status: str = "canonical") -> KnowledgeUnit:
        unit = make_unit(self.session, self.user, self.subject, status=status)
        self.session.add(
            UnitSection(
                user_id=self.user.id,
                subject_id=self.subject.id,
                unit_id=unit.id,
                section_id=section.id,
            )
        )
        self.session.flush()
        return unit

    def question(self, *sections: DocSection, **kw: Any) -> Question:
        self.n += 1
        kw.setdefault("source", "bank")
        if kw["source"] == "bank":
            kw.setdefault("bank_document_id", self.bank.id)
            kw.setdefault("bank_ord", self.n)
        q = make_question(self.session, self.user, self.subject, self.n, **kw)
        for s in sections:
            self.session.add(
                QuestionSection(
                    user_id=self.user.id,
                    subject_id=self.subject.id,
                    question_id=q.id,
                    section_id=s.id,
                )
            )
        self.session.flush()
        return q

    def get(self, subject_id: uuid.UUID | None = None) -> Any:
        return self.client.get(
            f"/v1/subjects/{subject_id or self.subject.id}/questions", headers=self.headers
        )

    def by_id(self) -> dict[str, dict[str, Any]]:
        response = self.get()
        assert response.status_code == 200
        return {row["id"]: row for row in response.json()["questions"]}


@pytest.fixture
def bench(client: TestClient, db_session: Session) -> Bench:
    user, headers = signed_in(db_session)
    return Bench(client, db_session, user, headers)


def test_ready_waiting_and_unlinked_each_get_their_line_us14_ac4_ac6(bench: Bench) -> None:
    done = bench.section("TCP")
    later = bench.section("UDP", studied=False)
    bench.card(done)
    bench.card(later)
    ready = bench.question(done)
    waiting = bench.question(done, later)
    loose = bench.question()
    rows = bench.by_id()
    assert rows[str(ready.id)]["status"] == "ready"
    assert rows[str(waiting.id)]["status"] == "waiting"
    assert rows[str(waiting.id)]["line"] == "Chờ học: mục 2"
    assert rows[str(waiting.id)]["waiting_sections"][0]["title"] == "UDP"
    assert rows[str(loose.id)]["status"] == "unlinked"
    assert rows[str(loose.id)]["line"] == "Chưa gắn mục. Sửa bằng thanh lệnh."


def test_summary_counts_total_ready_and_per_type_us14_ac6(bench: Bench) -> None:
    sec = bench.section("TCP")
    bench.card(sec)
    kind = make_type(bench.session, bench.user, bench.subject, name="Giải thích")
    bench.question(sec, type_id=kind.id)
    bench.question(sec, type_id=kind.id)
    bench.question()
    body = bench.get().json()
    assert body["total"] == 3
    assert body["ready"] == 2
    assert {t["name"]: t["count"] for t in body["types"]} == {"Giải thích": 2, "": 1}


def test_studied_section_without_a_canonical_card_still_waits_us14_ac4(bench: Bench) -> None:
    sec = bench.section("TCP")
    bench.card(sec, status="draft")
    q = bench.question(sec)
    assert bench.by_id()[str(q.id)]["status"] == "waiting"


def test_saving_the_last_needed_card_makes_the_question_ready_us14_ac4(bench: Bench) -> None:
    a, b = bench.section("TCP"), bench.section("UDP")
    bench.card(a)
    draft = bench.card(b, status="draft")
    q = bench.question(a, b)
    assert bench.by_id()[str(q.id)]["line"] == "Chờ học: mục 2"
    draft.status = "canonical"
    bench.session.flush()
    assert bench.by_id()[str(q.id)]["status"] == "ready"


def test_excluded_section_is_ignored_and_only_excluded_means_unlinked_us14_ac4(
    bench: Bench,
) -> None:
    kept = bench.section("TCP")
    skipped = bench.section("Phụ lục", studied=False, excluded=True)
    bench.card(kept)
    mixed = bench.question(kept, skipped)
    only = bench.question(skipped)
    rows = bench.by_id()
    assert rows[str(mixed.id)]["status"] == "ready"
    assert rows[str(only.id)]["status"] == "unlinked"


def test_a_section_under_an_excluded_parent_is_excluded_too_us14_ac4(bench: Bench) -> None:
    parent = bench.section("Chương", excluded=True)
    child = bench.section("Mục", studied=False, parent_id=parent.id)
    q = bench.question(child)
    assert bench.by_id()[str(q.id)]["status"] == "unlinked"


def test_question_on_many_sections_lists_all_waiting_in_natural_order_us14_ac4(
    bench: Bench,
) -> None:
    root = bench.section("Chương", studied=False)
    kids = [bench.section(f"M{i}", studied=False, parent_id=root.id, ord=i) for i in range(10)]
    q = bench.question(kids[9], kids[1])
    assert bench.by_id()[str(q.id)]["line"] == "Chờ học: mục 1.2, 1.10"


def test_partly_studied_section_is_not_studied_us14_ac4(bench: Bench) -> None:
    sec = bench.section("TCP", studied=False)
    sec.studied_weight = 1.0  # of 2.0
    bench.card(sec)
    q = bench.question(sec)
    assert bench.by_id()[str(q.id)]["status"] == "waiting"


def test_only_this_subjects_active_bank_questions_are_listed_us14_ac6(bench: Bench) -> None:
    sec = bench.section("TCP")
    mine = bench.question(sec)
    bench.question(sec, status="retired")
    bench.question(sec, source="review_auto")
    bench.question(sec, quality_status="rejected")
    bench.question(sec, source="generated")  # not kept yet
    other = make_subject(bench.session, bench.user, "Khác")
    make_question(
        bench.session,
        bench.user,
        other,
        99,
        source="bank",
        bank_ord=1,
        bank_document_id=make_document(
            bench.session,
            bench.user,
            other,
            sha="aa" * 32,
            role="question_bank",
            **indexed_fields(),
        ).id,
    )
    assert list(bench.by_id()) == [str(mine.id)]


def test_questions_come_in_bank_order_with_number_us14_ac6(bench: Bench) -> None:
    second = bench.question(bank_ord=2)
    first = bench.question(bank_ord=1)
    rows = bench.get().json()["questions"]
    assert [r["id"] for r in rows] == [str(first.id), str(second.id)]
    assert rows[0]["number"] == 1


def test_someone_elses_subject_is_a_404(bench: Bench, db_session: Session) -> None:
    other, _ = signed_in(db_session)
    theirs = make_subject(db_session, other)
    assert bench.get(theirs.id).status_code == 404


def test_requires_sign_in(bench: Bench) -> None:
    assert bench.client.get(f"/v1/subjects/{bench.subject.id}/questions").status_code in (401, 403)
