"""What the statistics screen and the CSV read (T9.4b, US-10): every query is scoped to the user and
to visible subjects. The rules are in `domain.stats` and `domain.progress`; nothing is stored for
the grid, it is read from what the learner did (decision D1 in the T9.4 notes)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select

from core_api.db.models import (
    Attempt,
    DocSection,
    Exam,
    KnowledgeUnit,
    MemoryState,
    PracticeState,
    Question,
    QuestionSection,
    QuestionType,
    ReviewSession,
    Subject,
    UnitRevision,
    UnitSection,
)
from core_api.domain.mastery import PracticeVerdict
from core_api.domain.readiness import Card, Ready, Section
from core_api.domain.readiness import readiness as question_readiness
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, Phase
from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
from core_api.domain.scheduling.practice import verdict_of
from core_api.domain.stats import ActivityEvent, BankQuestion, Leaf
from core_api.repositories.base import UserScopedRepository
from core_api.repositories.practice import PracticeLogRepository
from core_api.repositories.progress import ProgressRepository

_SCHEDULER = FsrsScheduler()
_LIVE_CARD = ("canonical",)
# A question that is not a pipeline review question: the learner's practice bank.
_BANK_SOURCES = ("bank", "generated")


@dataclass(frozen=True)
class SubjectInfo:
    id: uuid.UUID
    name: str
    exam_date: date | None
    created_at: datetime


def _state(row: MemoryState | PracticeState) -> State:
    return State(
        phase=Phase(row.phase),
        step=row.step,
        stability=row.stability,
        difficulty=row.difficulty,
        due=row.due,
        last_review=row.last_review,
    )


class StatsRepository(UserScopedRepository[MemoryState]):
    model = MemoryState
    _cached_sections: list[DocSection] | None = None

    def subjects(self) -> list[SubjectInfo]:
        rows = self.session.execute(
            select(Subject.id, Subject.name, Subject.created_at, func.min(Exam.exam_date))
            .join(
                Exam, (Exam.subject_id == Subject.id) & (Exam.user_id == self.user_id), isouter=True
            )
            .where(Subject.user_id == self.user_id, Subject.deleted_at.is_(None))
            .group_by(Subject.id)
            .order_by(Subject.name, Subject.id)
        ).all()
        return [SubjectInfo(sid, name, exam, created) for sid, name, created, exam in rows]

    def _sections(self) -> list[DocSection]:
        """The user's outline rows, read once per repository (one request)."""
        if self._cached_sections is None:
            self._cached_sections = list(
                self.session.scalars(select(DocSection).where(DocSection.user_id == self.user_id))
            )
        return self._cached_sections

    @staticmethod
    def _studied(section: DocSection) -> bool:
        return section.weight > 0 and section.studied_weight >= section.weight

    def leaves(self) -> dict[uuid.UUID, list[Leaf]]:
        """Leaf sections of each subject's outline: a leaf has no child."""
        sections = self._sections()
        parents = {s.parent_id for s in sections if s.parent_id is not None}
        out: dict[uuid.UUID, list[Leaf]] = {}
        for s in sections:
            if s.id not in parents:
                out.setdefault(s.subject_id, []).append(
                    Leaf(s.weight, s.unit, self._studied(s), s.excluded)
                )
        return out

    def section_titles(self) -> dict[uuid.UUID, str]:
        return {s.id: s.title for s in self._sections()}

    def retentions(self, now: datetime) -> dict[uuid.UUID, list[float]]:
        """Recall today of each live, not skipped card that has a core schedule, by subject."""
        rows = self.session.execute(
            select(KnowledgeUnit.subject_id, MemoryState)
            .join(
                MemoryState,
                (MemoryState.unit_id == KnowledgeUnit.id)
                & (MemoryState.user_id == self.user_id)
                & (MemoryState.facet == "core"),
            )
            .where(
                KnowledgeUnit.user_id == self.user_id,
                KnowledgeUnit.status.in_(_LIVE_CARD),
                KnowledgeUnit.skipped_at.is_(None),
            )
        ).all()
        out: dict[uuid.UUID, list[float]] = {}
        for subject_id, memory in rows:
            out.setdefault(subject_id, []).append(_SCHEDULER.retrievability(_state(memory), now))
        return out

    def bank(self, now: datetime) -> dict[uuid.UUID, list[BankQuestion]]:
        """The practice bank of each subject: active, quality-checked questions that are not
        pipeline review questions."""
        sections = {
            s.id: Section(s.id, s.title, self._studied(s), s.excluded) for s in self._sections()
        }
        links: dict[uuid.UUID, list[uuid.UUID]] = {}
        for qid, sid in self.session.execute(
            select(QuestionSection.question_id, QuestionSection.section_id).where(
                QuestionSection.user_id == self.user_id
            )
        ):
            links.setdefault(qid, []).append(sid)
        cards = [
            Card(section_id, True)
            for (section_id,) in self.session.execute(
                select(UnitSection.section_id)
                .join(KnowledgeUnit, KnowledgeUnit.id == UnitSection.unit_id)
                .where(
                    UnitSection.user_id == self.user_id,
                    KnowledgeUnit.status.in_(_LIVE_CARD),
                )
                .distinct()
            )
        ]
        states = {
            row.question_id: row
            for row in self.session.scalars(
                select(PracticeState).where(
                    PracticeState.user_id == self.user_id, PracticeState.removed_at.is_(None)
                )
            )
        }
        verdicts: dict[uuid.UUID, PracticeVerdict] = {}
        for review in PracticeLogRepository(self.session, self.user_id).effective():
            verdicts[review.question_id] = verdict_of(review.rating)  # oldest first: last wins
        questions = self.session.execute(
            select(Question.id, Question.subject_id, QuestionType.name)
            .join(
                QuestionType,
                (QuestionType.id == Question.type_id) & (QuestionType.user_id == self.user_id),
                isouter=True,
            )
            .where(
                Question.user_id == self.user_id,
                Question.status == "active",
                Question.quality_status == "ok",
                Question.source.in_(_BANK_SOURCES),
                # A generated candidate is a practice question only once kept (T9.6b, AC5).
                (Question.source != "generated") | Question.kept_at.is_not(None),
            )
        ).all()
        out: dict[uuid.UUID, list[BankQuestion]] = {}
        for qid, subject_id, type_name in questions:
            state = states.get(qid)
            recall = None if state is None else _SCHEDULER.retrievability(_state(state), now)
            ready = isinstance(question_readiness(links.get(qid, []), sections, cards), Ready)
            out.setdefault(subject_id, []).append(
                BankQuestion(
                    question_type=type_name or "",
                    ready=ready,
                    practiced=state is not None,
                    retrievability=recall,
                    last_verdict=verdicts.get(qid),
                )
            )
        return out

    def events(self) -> list[ActivityEvent]:
        """Cards saved (a card's learner revision, rev 1) and questions answered (submitted
        attempts, review and practice alike), one event each; sections spread over extra events
        that add no count."""
        events: list[ActivityEvent] = []
        unit_sections: dict[uuid.UUID, list[uuid.UUID]] = {}
        for unit_id, section_id in self.session.execute(
            select(UnitSection.unit_id, UnitSection.section_id).where(
                UnitSection.user_id == self.user_id
            )
        ):
            unit_sections.setdefault(unit_id, []).append(section_id)
        saved = self.session.execute(
            select(UnitRevision.unit_id, UnitRevision.created_at, KnowledgeUnit.subject_id)
            .join(KnowledgeUnit, KnowledgeUnit.id == UnitRevision.unit_id)
            .where(
                UnitRevision.user_id == self.user_id,
                UnitRevision.rev == 1,
                UnitRevision.origin == "user",
                KnowledgeUnit.user_id == self.user_id,
                KnowledgeUnit.status.in_(_LIVE_CARD),
            )
        ).all()
        for unit_id, at, subject_id in saved:
            events += _spread(at, subject_id, unit_sections.get(unit_id, []), cards=True)
        question_sections: dict[uuid.UUID, list[uuid.UUID]] = {}
        for question_id, section_id in self.session.execute(
            select(QuestionSection.question_id, QuestionSection.section_id).where(
                QuestionSection.user_id == self.user_id
            )
        ):
            question_sections.setdefault(question_id, []).append(section_id)
        answered = self.session.execute(
            select(Attempt.question_id, Attempt.submitted_at, Question.subject_id)
            .join(Question, Question.id == Attempt.question_id)
            .where(
                Attempt.user_id == self.user_id,
                Attempt.status == "submitted",
                Question.user_id == self.user_id,
            )
        ).all()
        for question_id, at, subject_id in answered:
            events += _spread(at, subject_id, question_sections.get(question_id, []), cards=False)
        return events


def _spread(
    at: datetime, subject_id: uuid.UUID, sections: list[uuid.UUID], *, cards: bool
) -> list[ActivityEvent]:
    ids: list[uuid.UUID | None] = sorted(sections, key=str) or [None]
    return [
        ActivityEvent(
            at=at,
            subject_id=subject_id,
            section_id=section_id,
            cards_saved=int(cards and i == 0),
            questions_answered=int(not cards and i == 0),
        )
        for i, section_id in enumerate(ids)
    ]


class ExportRepository(ProgressRepository):
    """The CSV's source: as `ProgressRepository`, but a sitting left open counts hours up to the
    last answer submitted in it (US-10 AC4, T5.5a)."""

    def _review_sittings(self) -> list[tuple[date, datetime, datetime | None]]:
        last = (
            select(Attempt.review_session_id, func.max(Attempt.submitted_at).label("last"))
            .where(Attempt.user_id == self.user_id, Attempt.status == "submitted")
            .group_by(Attempt.review_session_id)
            .subquery()
        )
        rows = self.session.execute(
            select(
                ReviewSession.learning_day,
                ReviewSession.started_at,
                ReviewSession.ended_at,
                last.c.last,
            )
            .join(last, last.c.review_session_id == ReviewSession.id, isouter=True)
            .where(ReviewSession.user_id == self.user_id)
            .order_by(ReviewSession.learning_day, ReviewSession.started_at)
        ).all()
        out: list[tuple[date, datetime, datetime | None]] = []
        for day, started, ended, last_answer in rows:
            if ended is None and last_answer is not None and last_answer > started:
                ended = last_answer
            out.append((day, started, ended))
        return out
