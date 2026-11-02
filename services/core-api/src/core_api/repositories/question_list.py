"""A subject's bank questions with their readiness (T8.2, US-14 AC3-AC6).

Readiness is computed from the rows on every read (domain.readiness), so a card saved later flips
a question with no extra step (AC4). A section counts as excluded when it or an ancestor is.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.db.models import (
    DocSection,
    KnowledgeUnit,
    Question,
    QuestionSection,
    QuestionType,
    UnitSection,
)
from core_api.domain.readiness import (
    Card,
    OutlineNode,
    Readiness,
    Section,
    Waiting,
    outline_numbers,
    readiness,
)

_BANK_SOURCES = ("bank", "generated")


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


class QuestionListRepository:
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id

    def _sections(self, subject_id: uuid.UUID) -> dict[uuid.UUID, Section]:
        rows = list(
            self.session.scalars(
                select(DocSection).where(
                    DocSection.user_id == self.user_id, DocSection.subject_id == subject_id
                )
            )
        )
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
                numbers[r.id],
                r.weight > 0 and r.studied_weight >= r.weight,
                excluded(r),
            )
            for r in rows
        }

    def list(self, subject_id: uuid.UUID) -> list[ListedQuestion]:
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
                )
            )
        return out
