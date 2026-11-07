"""Readiness guard: the question list, `ready_ids` (Today, practice) and the stats bank all say
the same questions are Ready, and that matches `domain.readiness`, whatever the sequence of
writes. Readiness is computed on every read (no cache), so this is the test that catches one of
the three readers drifting from the others."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import (
    DocSection,
    KnowledgeUnit,
    Question,
    QuestionSection,
    Subject,
    UnitSection,
    User,
)
from core_api.domain.readiness import Card, Ready, Section, Waiting, readiness
from core_api.repositories.question_list import QuestionListRepository
from core_api.repositories.stats import StatsRepository
from core_api.repositories.today import TodayRepository
from v2_rows import make_document, make_question, make_section, make_subject, make_unit

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
N_SECTIONS = 5
N_QUESTIONS = 4
SEC = st.integers(0, N_SECTIONS - 1)
QUE = st.integers(0, N_QUESTIONS - 1)
OPS = st.lists(
    st.one_of(
        st.tuples(st.just("add_card"), SEC, st.sampled_from(["canonical", "draft", "retired"])),
        st.tuples(st.just("add_card_loose"), st.just(0), st.just("canonical")),
        st.tuples(st.just("remove_card"), st.integers(0, 6), st.just("")),
        st.tuples(st.just("move_card"), st.integers(0, 6), SEC),
        st.tuples(st.just("exclude"), SEC, st.booleans()),
        st.tuples(st.just("studied"), SEC, st.sampled_from([0.0, 1.0, 2.0, 4.0])),
        st.tuples(st.just("weight"), SEC, st.sampled_from([0.0, 2.0, 4.0])),
        st.tuples(st.just("link"), QUE, SEC),
        st.tuples(st.just("unlink"), QUE, SEC),
        st.tuples(st.just("qstatus"), QUE, st.sampled_from(["active", "retired"])),
        st.tuples(st.just("quality"), QUE, st.sampled_from(["ok", "pending", "rejected"])),
    ),
    max_size=14,
)
PARENTS = st.lists(
    st.one_of(st.none(), st.integers(0, 3)), min_size=N_SECTIONS, max_size=N_SECTIONS
)


@dataclass
class World:
    session: Session
    user: User
    subject: Subject
    sections: list[DocSection]
    questions: list[Question]
    units: list[KnowledgeUnit] = field(default_factory=lambda: [])
    unit_section: list[uuid.UUID | None] = field(default_factory=lambda: [])  # parallel to units

    def links(self) -> set[tuple[uuid.UUID, uuid.UUID]]:
        ids = {q.id for q in self.questions}
        rows = self.session.execute(
            select(QuestionSection.question_id, QuestionSection.section_id)
        ).all()
        return {(q, s) for q, s in rows if q in ids}

    def expected(self) -> set[uuid.UUID]:
        """The Ready questions by the rules of domain.readiness, from the model alone."""
        by_id = {s.id: s for s in self.sections}

        def excluded(s: DocSection) -> bool:
            while True:
                if s.excluded:
                    return True
                if s.parent_id is None:
                    return False
                s = by_id[s.parent_id]

        outline = {
            s.id: Section(s.id, s.title, s.weight > 0 and s.studied_weight >= s.weight, excluded(s))
            for s in self.sections
        }
        cards = [
            Card(sid, True)
            for unit, sid in zip(self.units, self.unit_section, strict=True)
            if sid is not None and unit.status == "canonical"
        ]
        linked: dict[uuid.UUID, list[uuid.UUID]] = {}
        for q_id, sec_id in self.links():
            linked.setdefault(q_id, []).append(sec_id)
        return {
            q.id
            for q in self.questions
            if q.status == "active"
            and q.quality_status == "ok"
            and isinstance(readiness(linked.get(q.id, []), outline, cards), Ready)
        }


def build(session: Session, parents: list[int | None]) -> World:
    user, _ = signed_in(session)
    subject = make_subject(session, user)
    book = make_document(session, user, subject, sha=uuid.uuid4().hex * 2, role="textbook")
    sections: list[DocSection] = []
    for i, parent in enumerate(parents):
        parent_id = sections[parent].id if parent is not None and parent < i else None
        sections.append(
            make_section(
                session,
                user,
                book,
                title=f"{i + 1}. Mục",
                ord=i,
                parent_id=parent_id,
                weight=2.0,
                studied_weight=2.0,
            )
        )
    questions = [
        make_question(session, user, subject, n, source="generated", kept_at=NOW)
        for n in range(N_QUESTIONS)
    ]
    return World(session, user, subject, sections, questions)


def link_card(w: World, unit: KnowledgeUnit, section_id: uuid.UUID) -> None:
    w.session.add(
        UnitSection(
            user_id=w.user.id, subject_id=w.subject.id, unit_id=unit.id, section_id=section_id
        )
    )


def apply(w: World, op: tuple[str, Any, Any]) -> None:
    name: str = op[0]
    a: int = op[1]
    b: Any = op[2]
    sec_b: int = b if isinstance(b, int) else 0
    s = w.session
    if name in ("add_card", "add_card_loose"):
        unit = make_unit(s, w.user, w.subject, status=b)
        sec = None if name == "add_card_loose" else w.sections[a].id
        if sec is not None:
            link_card(w, unit, sec)
        w.units.append(unit)
        w.unit_section.append(sec)
    elif name in ("remove_card", "move_card") and w.units:
        k = a % len(w.units)
        s.execute(delete(UnitSection).where(UnitSection.unit_id == w.units[k].id))
        w.unit_section[k] = None
        if name == "move_card":
            link_card(w, w.units[k], w.sections[sec_b].id)
            w.unit_section[k] = w.sections[sec_b].id
    elif name == "exclude":
        w.sections[a].excluded = bool(b)
    elif name == "studied":
        w.sections[a].studied_weight = float(b)
    elif name == "weight":
        w.sections[a].weight = float(b)
    elif name == "link":
        if (w.questions[a].id, w.sections[sec_b].id) not in w.links():
            s.add(
                QuestionSection(
                    user_id=w.user.id,
                    subject_id=w.subject.id,
                    question_id=w.questions[a].id,
                    section_id=w.sections[sec_b].id,
                )
            )
    elif name == "unlink":
        s.execute(
            delete(QuestionSection).where(
                QuestionSection.question_id == w.questions[a].id,
                QuestionSection.section_id == w.sections[sec_b].id,
            )
        )
    elif name == "qstatus":
        w.questions[a].status = str(b)
    elif name == "quality":
        w.questions[a].quality_status = str(b)
    s.flush()


def readers(w: World) -> tuple[set[uuid.UUID], set[uuid.UUID], int]:
    repo = QuestionListRepository(w.session, w.user.id)
    listed = {q.id for q in repo.list_for_subject(w.subject.id, NOW) if isinstance(q.state, Ready)}
    ready = set(repo.ready_ids())
    bank = StatsRepository(w.session, w.user.id).bank(NOW)
    return listed, ready, sum(1 for q in bank.get(w.subject.id, []) if q.ready)


@settings(
    max_examples=40,
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(parents=PARENTS, ops=OPS)
def check_sequence(session: Session, parents: list[int | None], ops: list[Any]) -> None:
    nested = session.begin_nested()
    try:
        w = build(session, parents)
        for step, op in enumerate(ops):
            apply(w, op)
            expected = w.expected()
            listed, ready, stats_ready = readers(w)
            where = f"after step {step} {op} (parents {parents})"
            assert listed == expected, f"question list differs {where}"
            assert ready == expected, f"ready_ids differs {where}"
            assert stats_ready == len(expected), f"stats bank differs {where}"
    finally:
        nested.rollback()


def test_readers_agree_on_ready_questions_for_any_write_sequence(db_session: Session) -> None:
    check_sequence(db_session)


def test_card_with_no_section_leaves_question_waiting(db_session: Session) -> None:
    """A card not linked to any section unlocks nothing: the question stays Waiting."""
    w = build(db_session, [None] * N_SECTIONS)
    w.sections[0].studied_weight = 0.0
    apply(w, ("link", 0, 0))
    apply(w, ("add_card_loose", 0, "canonical"))
    repo = QuestionListRepository(db_session, w.user.id)
    states = {q.id: q.state for q in repo.list_for_subject(w.subject.id, NOW)}
    assert isinstance(states[w.questions[0].id], Waiting)
    listed, ready, stats_ready = readers(w)
    assert (listed, ready, stats_ready) == (set(), set(), 0)


def test_today_computes_ready_ids_once_per_request(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = build(db_session, [None] * N_SECTIONS)
    calls: list[int] = []
    real = QuestionListRepository.ready_ids

    def counting(self: QuestionListRepository) -> dict[uuid.UUID, uuid.UUID]:
        calls.append(1)
        return real(self)

    monkeypatch.setattr(QuestionListRepository, "ready_ids", counting)
    reads = TodayRepository(db_session, w.user.id)
    reads.practice_candidates()
    reads.has_practice()
    assert len(calls) == 1


def test_excluded_ancestor_makes_child_not_ready_in_every_reader(db_session: Session) -> None:
    w = build(db_session, [None, 0, None, None, None])
    apply(w, ("add_card", 1, "canonical"))
    apply(w, ("link", 0, 1))
    assert readers(w) == ({w.questions[0].id}, {w.questions[0].id}, 1)
    apply(w, ("exclude", 0, True))
    assert readers(w) == (set(), set(), 0)
