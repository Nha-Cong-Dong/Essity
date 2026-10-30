"""What `compose_today` reads (T2.8, ARCH §5.3): every scheduled unit with the question that asks
about it, and every new question. Visible subjects only (not soft-deleted), active units and
questions only. One query each, whatever the number of units (US-03 AC2: under 300 ms)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, and_, exists, func, select

from core_api.db.models import KnowledgeUnit, MemoryState, Question, QuestionUnit, Subject
from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
from core_api.domain.scheduling.fsrs_adapter import Phase
from core_api.domain.today import RECALL_LEVEL, DueUnit, NewQuestion
from core_api.repositories.base import UserScopedRepository


class TodayRepository(UserScopedRepository[MemoryState]):
    model = MemoryState

    def _visible_subject(self, subject_id: object) -> object:
        return exists().where(
            Subject.id == subject_id,
            Subject.user_id == self.user_id,
            Subject.deleted_at.is_(None),
        )

    def _questions_with_skipped_unit(self) -> list[uuid.UUID]:
        """A question that checks a skipped unit stops being chosen (T2.23, PLAN). Read as a short
        list (nearly always empty) and passed as values: as a subquery inside NOT IN, stale
        statistics made the planner rescan it per question (T2.8 timing test)."""
        query = (
            select(QuestionUnit.question_id)
            .join(
                KnowledgeUnit,
                and_(
                    KnowledgeUnit.id == QuestionUnit.unit_id,
                    KnowledgeUnit.user_id == self.user_id,
                ),
            )
            .where(QuestionUnit.user_id == self.user_id, KnowledgeUnit.skipped_at.is_not(None))
        )
        return list(self.session.scalars(query))

    def _not_skipped(self) -> list[ColumnElement[bool]]:
        """The condition "no unit of the question is skipped", none at all when nothing is: an
        empty NOT IN costs the planner a subquery per row."""
        skipped = self._questions_with_skipped_unit()
        return [Question.id.not_in(skipped)] if skipped else []

    def unasked_by_subject(self) -> dict[uuid.UUID, int]:
        """Units never asked, by visible subject: what the exam quota counts (T2.23, b2)."""
        scheduled = select(MemoryState.unit_id).where(
            MemoryState.user_id == self.user_id, MemoryState.facet == "core"
        )
        rows = self.session.execute(
            select(KnowledgeUnit.subject_id, func.count())
            .where(
                KnowledgeUnit.user_id == self.user_id,
                KnowledgeUnit.status == "active",
                KnowledgeUnit.skipped_at.is_(None),
                KnowledgeUnit.id.not_in(scheduled),
                self._visible_subject(KnowledgeUnit.subject_id),  # type: ignore[arg-type]
            )
            .group_by(KnowledgeUnit.subject_id)
        ).all()
        return {subject_id: count for subject_id, count in rows}

    def scheduled_units(self) -> Sequence[DueUnit]:
        """Every (unit, core) with a schedule, due or not, and its first active question: the
        one asked for it. Only level-1 questions are asked (T5.R): levels 2 and 3 are practice
        made on demand, outside today and FSRS."""
        first_question = (
            select(QuestionUnit.unit_id, Question.id.label("question_id"))
            .join(
                Question,
                and_(Question.id == QuestionUnit.question_id, Question.user_id == self.user_id),
            )
            .where(
                QuestionUnit.user_id == self.user_id,
                Question.status == "active",
                Question.level == RECALL_LEVEL,
                *self._not_skipped(),
            )
            .order_by(QuestionUnit.unit_id, Question.created_at, Question.id)
            .distinct(QuestionUnit.unit_id)
            .subquery()
        )
        rows = self.session.execute(
            select(MemoryState, KnowledgeUnit.subject_id, first_question.c.question_id)
            .join(
                KnowledgeUnit,
                and_(
                    KnowledgeUnit.id == MemoryState.unit_id,
                    KnowledgeUnit.user_id == self.user_id,
                ),
            )
            .join(first_question, first_question.c.unit_id == MemoryState.unit_id)
            .where(
                MemoryState.user_id == self.user_id,
                MemoryState.facet == "core",
                KnowledgeUnit.status == "active",
                KnowledgeUnit.skipped_at.is_(None),
                self._visible_subject(KnowledgeUnit.subject_id),  # type: ignore[arg-type]
            )
        ).all()
        return [
            DueUnit(
                unit_id=row.unit_id,
                subject_id=subject_id,
                question_id=question_id,
                state=State(
                    phase=Phase(row.phase),
                    step=row.step,
                    stability=row.stability,
                    difficulty=row.difficulty,
                    due=row.due,
                    last_review=row.last_review,
                ),
            )
            for row, subject_id, question_id in rows
        ]

    def schedules_of(self, question_id: uuid.UUID) -> Sequence[State]:
        """The core schedules of the active, not skipped units of a question (US-07): empty when
        none of them has been reviewed."""
        rows = self.session.scalars(
            select(MemoryState)
            .join(
                QuestionUnit,
                and_(
                    QuestionUnit.unit_id == MemoryState.unit_id,
                    QuestionUnit.user_id == self.user_id,
                ),
            )
            .join(
                KnowledgeUnit,
                and_(
                    KnowledgeUnit.id == MemoryState.unit_id,
                    KnowledgeUnit.user_id == self.user_id,
                ),
            )
            .where(
                MemoryState.user_id == self.user_id,
                MemoryState.facet == "core",
                QuestionUnit.question_id == question_id,
                KnowledgeUnit.status == "active",
                KnowledgeUnit.skipped_at.is_(None),
            )
        ).all()
        return [
            State(
                phase=Phase(row.phase),
                step=row.step,
                stability=row.stability,
                difficulty=row.difficulty,
                due=row.due,
                last_review=row.last_review,
            )
            for row in rows
        ]

    def new_questions(self) -> Sequence[NewQuestion]:
        """Active questions with a unit never asked and none skipped (a question of several units
        stays new while one of them has no schedule: T2.23 fixes the old "none reviewed" rule,
        which left that unit never asked). A question linked to no unit counts as new."""
        # Sets, not a correlated NOT EXISTS: NOT IN hashes each once. A correlated NOT EXISTS let
        # the planner, misled by stale statistics, rescan it per question (7 s for 500 questions
        # instead of 6 ms; T2.8 timing test).
        scheduled = select(MemoryState.unit_id).where(
            MemoryState.user_id == self.user_id, MemoryState.facet == "core"
        )
        unasked_pairs = (
            select(QuestionUnit.question_id, QuestionUnit.unit_id)
            .join(
                KnowledgeUnit,
                and_(
                    KnowledgeUnit.id == QuestionUnit.unit_id,
                    KnowledgeUnit.user_id == self.user_id,
                ),
            )
            .where(
                QuestionUnit.user_id == self.user_id,
                KnowledgeUnit.status == "active",
                KnowledgeUnit.skipped_at.is_(None),
                KnowledgeUnit.id.not_in(scheduled),
            )
        )
        with_unasked = select(unasked_pairs.subquery().c.question_id)
        linked = select(QuestionUnit.question_id).where(QuestionUnit.user_id == self.user_id)
        unlinked = select(Question.id).where(
            Question.user_id == self.user_id, Question.id.not_in(linked)
        )
        candidates = with_unasked.union(unlinked).subquery()
        unasked_units: dict[uuid.UUID, set[uuid.UUID]] = {}
        for question_id, unit_id in self.session.execute(unasked_pairs):
            unasked_units.setdefault(question_id, set()).add(unit_id)
        rows = self.session.execute(
            select(Question.id, Question.subject_id, Question.created_at).where(
                Question.user_id == self.user_id,
                Question.status == "active",
                Question.level == RECALL_LEVEL,
                Question.id.in_(select(candidates.c.question_id)),
                *self._not_skipped(),
                self._visible_subject(Question.subject_id),  # type: ignore[arg-type]
            )
        ).all()
        return [
            NewQuestion(
                question_id=id,
                subject_id=subject_id,
                created_at=created_at,
                unasked_units=frozenset(unasked_units.get(id, ())),
            )
            for id, subject_id, created_at in rows
        ]

    def has_questions(self) -> bool:
        """Whether a visible subject has an active question at all."""
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        Question.user_id == self.user_id,
                        Question.status == "active",
                        Question.level == RECALL_LEVEL,
                        self._visible_subject(Question.subject_id),  # type: ignore[arg-type]
                    )
                )
            )
        )
