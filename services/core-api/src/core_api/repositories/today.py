"""What `compose_today` reads (T2.8, ARCH §5.3): every scheduled unit with the question that asks
about it, and every new question. Visible subjects only (not soft-deleted), active units and
questions only. One query each, whatever the number of units (US-03 AC2: under 300 ms)."""

from collections.abc import Sequence

from sqlalchemy import and_, exists, select

from core_api.db.models import KnowledgeUnit, MemoryState, Question, QuestionUnit, Subject
from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
from core_api.domain.scheduling.fsrs_adapter import Phase
from core_api.domain.today import DueUnit, NewQuestion
from core_api.repositories.base import UserScopedRepository


class TodayRepository(UserScopedRepository[MemoryState]):
    model = MemoryState

    def _visible_subject(self, subject_id: object) -> object:
        return exists().where(
            Subject.id == subject_id,
            Subject.user_id == self.user_id,
            Subject.deleted_at.is_(None),
        )

    def scheduled_units(self) -> Sequence[DueUnit]:
        """Every (unit, core) with a schedule, due or not, and its first active question: the
        one asked for it until the level ladder (T5.2)."""
        first_question = (
            select(QuestionUnit.unit_id, Question.id.label("question_id"))
            .join(
                Question,
                and_(Question.id == QuestionUnit.question_id, Question.user_id == self.user_id),
            )
            .where(QuestionUnit.user_id == self.user_id, Question.status == "active")
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

    def new_questions(self) -> Sequence[NewQuestion]:
        """Active questions none of whose units has a schedule yet."""
        # The questions with a scheduled unit, as one set: NOT IN hashes it once. A correlated
        # NOT EXISTS let the planner, misled by stale statistics, rescan it per question (7 s
        # for 500 questions instead of 6 ms; T2.8 timing test).
        reviewed = (
            select(QuestionUnit.question_id)
            .join(
                MemoryState,
                and_(
                    MemoryState.unit_id == QuestionUnit.unit_id,
                    MemoryState.user_id == self.user_id,
                ),
            )
            .where(QuestionUnit.user_id == self.user_id)
        )
        rows = self.session.execute(
            select(Question.id, Question.subject_id, Question.created_at).where(
                Question.user_id == self.user_id,
                Question.status == "active",
                Question.id.not_in(reviewed),
                self._visible_subject(Question.subject_id),  # type: ignore[arg-type]
            )
        ).all()
        return [
            NewQuestion(question_id=id, subject_id=subject_id, created_at=created_at)
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
                        self._visible_subject(Question.subject_id),  # type: ignore[arg-type]
                    )
                )
            )
        )
