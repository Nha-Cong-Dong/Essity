"""A subject's bank questions with their readiness (T8.2, US-14 AC3-AC6).

Readiness is computed from the rows on every read (domain.readiness), so a card saved later flips
a question with no extra step (AC4). A section counts as excluded when it or an ancestor is.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select

from core_api.db.models import (
    DocSection,
    KnowledgeUnit,
    PracticeState,
    Question,
    QuestionSection,
    QuestionType,
    Subject,
    UnitSection,
)
from core_api.domain.readiness import (
    Card,
    OutlineNode,
    Readiness,
    Ready,
    Section,
    Waiting,
    outline_numbers,
    printed_number,
    readiness,
)
from core_api.repositories.base import UserScopedRepository

_BANK_SOURCES = ("bank", "generated")
PREREQ_CARD_CAP = 8  # prerequisite cards shown for one question


@dataclass(frozen=True)
class PrereqCard:
    id: uuid.UUID
    title: str
    summary: str


@dataclass(frozen=True)
class ListedQuestion:
    id: uuid.UUID
    number: int | None
    prompt: str
    type_name: str
    origin: str  # "bank" | "generated"
    answer_source: str  # "bank" | "ai": where the answer text came from
    state: Readiness
    waiting_titles: dict[uuid.UUID, str]  # section id -> title, for the waiting sections
    unlocked_at: datetime | None = None  # when its last section got its first card (ready only)
    due: bool = False  # ready, and never practised or due now (V19, V20)
    prerequisite_cards: tuple[PrereqCard, ...] = ()  # ready only: the first card of each section


class QuestionListRepository(UserScopedRepository[Question]):
    model = Question

    def _sections(self, subject_id: uuid.UUID | None = None) -> dict[uuid.UUID, Section]:
        """The user's sections, of one subject or (None) of every subject."""
        query = select(DocSection).where(DocSection.user_id == self.user_id)
        if subject_id is not None:
            query = query.where(DocSection.subject_id == subject_id)
        rows = list(self.session.scalars(query))
        by_id = {r.id: r for r in rows}

        def excluded(row: DocSection) -> bool:
            seen: set[uuid.UUID] = set()
            node: DocSection | None = row
            while node is not None and node.id not in seen:
                if node.excluded:
                    return True
                seen.add(node.id)
                node = by_id.get(node.parent_id) if node.parent_id else None
            return False

        numbers: dict[uuid.UUID, str] = {}
        for document_id in {r.document_id for r in rows}:
            numbers.update(
                outline_numbers(
                    [
                        OutlineNode(r.id, r.parent_id, r.ord)
                        for r in rows
                        if r.document_id == document_id
                    ]
                )
            )
        return {
            r.id: Section(
                r.id,
                printed_number(r.title) or numbers[r.id],
                r.weight > 0 and r.studied_weight >= r.weight,
                excluded(r),
            )
            for r in rows
        }

    def list_for_subject(
        self, subject_id: uuid.UUID, now: datetime | None = None
    ) -> list[ListedQuestion]:
        """The subject's questions in bank order."""
        sections = self._sections(subject_id)
        titles = {
            sid: title
            for sid, title in self.session.execute(
                select(DocSection.id, DocSection.title).where(
                    DocSection.user_id == self.user_id, DocSection.subject_id == subject_id
                )
            )
        }
        links: dict[uuid.UUID, list[uuid.UUID]] = {}
        for qid, sid in self.session.execute(
            select(QuestionSection.question_id, QuestionSection.section_id).where(
                QuestionSection.user_id == self.user_id, QuestionSection.subject_id == subject_id
            )
        ):
            links.setdefault(qid, []).append(sid)
        cards = [
            Card(sid, True)
            for (sid,) in self.session.execute(
                select(UnitSection.section_id)
                .join(KnowledgeUnit, KnowledgeUnit.id == UnitSection.unit_id)
                .where(
                    UnitSection.user_id == self.user_id,
                    UnitSection.subject_id == subject_id,
                    KnowledgeUnit.status == "canonical",
                )
                .distinct()
            )
        ]
        first_card: dict[uuid.UUID, datetime] = {
            sid: at
            for sid, at in self.session.execute(
                select(UnitSection.section_id, func.min(KnowledgeUnit.created_at))
                .join(KnowledgeUnit, KnowledgeUnit.id == UnitSection.unit_id)
                .where(
                    UnitSection.user_id == self.user_id,
                    UnitSection.subject_id == subject_id,
                    KnowledgeUnit.status == "canonical",
                )
                .group_by(UnitSection.section_id)
            )
        }
        # The earliest canonical card of each section, in outline order (the prerequisite box).
        section_ord = {
            sid: ordinal
            for sid, ordinal in self.session.execute(
                select(DocSection.id, DocSection.ord).where(
                    DocSection.user_id == self.user_id, DocSection.subject_id == subject_id
                )
            )
        }
        first_unit: dict[uuid.UUID, PrereqCard] = {}
        for sid, uid, title, summary in self.session.execute(
            select(
                UnitSection.section_id, KnowledgeUnit.id, KnowledgeUnit.title, KnowledgeUnit.summary
            )
            .join(KnowledgeUnit, KnowledgeUnit.id == UnitSection.unit_id)
            .where(
                UnitSection.user_id == self.user_id,
                UnitSection.subject_id == subject_id,
                KnowledgeUnit.user_id == self.user_id,
                KnowledgeUnit.status == "canonical",
            )
            .order_by(KnowledgeUnit.created_at.desc(), KnowledgeUnit.id.desc())
        ):
            first_unit[sid] = PrereqCard(uid, title, summary)  # the last write is the earliest
        practice_due: dict[uuid.UUID, datetime] = {
            qid: due
            for qid, due in self.session.execute(
                select(PracticeState.question_id, PracticeState.due).where(
                    PracticeState.user_id == self.user_id, PracticeState.removed_at.is_(None)
                )
            )
        }
        rows = self.session.execute(
            select(Question, QuestionType.name)
            .join(
                QuestionType,
                (QuestionType.id == Question.type_id) & (QuestionType.user_id == self.user_id),
                isouter=True,
            )
            .where(
                Question.user_id == self.user_id,
                Question.subject_id == subject_id,
                Question.status == "active",
                Question.quality_status == "ok",
                Question.source.in_(_BANK_SOURCES),
                # A generated candidate is a practice question only once kept (T9.6b, AC5).
                (Question.source != "generated") | Question.kept_at.is_not(None),
            )
            .order_by(Question.bank_ord.nulls_last(), Question.created_at, Question.id)
        ).all()
        out: list[ListedQuestion] = []
        for question, type_name in rows:
            state = readiness(links.get(question.id, []), sections, cards)
            ready = isinstance(state, Ready)
            unlocked = [first_card[sid] for sid in links.get(question.id, []) if sid in first_card]
            prereq: list[PrereqCard] = []
            if ready:
                for sid in sorted(links.get(question.id, []), key=lambda x: section_ord.get(x, 0)):
                    card = first_unit.get(sid)
                    if card is not None and card not in prereq:
                        prereq.append(card)
            out.append(
                ListedQuestion(
                    id=question.id,
                    number=question.bank_ord,
                    prompt=question.prompt,
                    type_name=type_name or "",
                    origin=question.source,
                    answer_source="ai" if question.answer_origin == "ai" else "bank",
                    state=state,
                    waiting_titles={}
                    if not isinstance(state, Waiting)
                    else {s.id: titles.get(s.id, "") for s in state.sections},
                    unlocked_at=max(unlocked) if ready and unlocked else None,
                    prerequisite_cards=tuple(prereq[:PREREQ_CARD_CAP]),
                    due=ready
                    and now is not None
                    and (question.id not in practice_due or practice_due[question.id] <= now),
                )
            )
        return out

    def ready_ids(self) -> dict[uuid.UUID, uuid.UUID]:
        """Ready practice questions of every visible subject, as question id -> subject id, in a
        fixed number of queries whatever the number of subjects (T8.5; the same rules as
        `list_for_subject`: bank or kept generated, active, quality ok, `readiness` Ready)."""
        sections = self._sections()
        links: dict[uuid.UUID, list[uuid.UUID]] = {}
        for qid, sid in self.session.execute(
            select(QuestionSection.question_id, QuestionSection.section_id).where(
                QuestionSection.user_id == self.user_id
            )
        ):
            links.setdefault(qid, []).append(sid)
        cards = [
            Card(sid, True)
            for (sid,) in self.session.execute(
                select(UnitSection.section_id)
                .join(KnowledgeUnit, KnowledgeUnit.id == UnitSection.unit_id)
                .where(UnitSection.user_id == self.user_id, KnowledgeUnit.status == "canonical")
                .distinct()
            )
        ]
        rows = self.session.execute(
            select(Question.id, Question.subject_id)
            .join(
                Subject,
                (Subject.id == Question.subject_id)
                & (Subject.user_id == self.user_id)
                & Subject.deleted_at.is_(None),
            )
            .where(
                Question.user_id == self.user_id,
                Question.status == "active",
                Question.quality_status == "ok",
                Question.source.in_(_BANK_SOURCES),
                (Question.source != "generated") | Question.kept_at.is_not(None),
            )
        ).all()
        return {
            qid: subject_id
            for qid, subject_id in rows
            if isinstance(readiness(links.get(qid, []), sections, cards), Ready)
        }
