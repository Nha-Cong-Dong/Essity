"""What `compose_today` reads (T2.8, ARCH §5.3): every scheduled unit with the question that asks
about it, and every new question. Visible subjects only (not soft-deleted), active units and
questions only. One query each, whatever the number of units (US-03 AC2: under 300 ms)."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, and_, exists, func, select

from core_api.db.models import (
    Attempt,
    Grade,
    GradeUnit,
    KnowledgeUnit,
    MemoryState,
    Question,
    QuestionUnit,
    Subject,
)
from core_api.domain.ladder import (
    LadderConfig,
    LadderQuestion,
    choose_for_unit,
    is_eligible,
    load_ladder_config,
)
from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
from core_api.domain.scheduling.fsrs_adapter import Phase
from core_api.domain.today import DueUnit, NewQuestion
from core_api.repositories.base import UserScopedRepository


class TodayRepository(UserScopedRepository[MemoryState]):
    model = MemoryState
    ladder: LadderConfig = load_ladder_config()  # versioned thresholds (T5.2, Q19 tạm)

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

    def correct_counts(self) -> dict[tuple[uuid.UUID, int], int]:
        """Correct answers so far by (unit, question level): the newest grade of each attempt, its
        verdict on the unit "correct" (T5.2, US-03 AC3)."""
        newest = (
            select(Grade.attempt_id, func.max(Grade.seq).label("seq"))
            .where(Grade.user_id == self.user_id)
            .group_by(Grade.attempt_id)
            .subquery()
        )
        rows = self.session.execute(
            select(GradeUnit.unit_id, Question.level, func.count())
            .join(Grade, Grade.id == GradeUnit.grade_id)
            .join(newest, (newest.c.attempt_id == Grade.attempt_id) & (newest.c.seq == Grade.seq))
            .join(Attempt, Attempt.id == Grade.attempt_id)
            .join(Question, Question.id == Attempt.question_id)
            .where(
                GradeUnit.user_id == self.user_id,
                Grade.user_id == self.user_id,
                Attempt.user_id == self.user_id,
                Attempt.status == "submitted",
                Question.user_id == self.user_id,
                GradeUnit.verdict == "correct",
            )
            .group_by(GradeUnit.unit_id, Question.level)
        ).all()
        return {(unit_id, level): count for unit_id, level, count in rows}

    def _ladder_questions(self) -> dict[uuid.UUID, LadderQuestion]:
        """Active questions not on a skipped unit, with every unit they check."""
        rows = self.session.execute(
            select(Question.id, Question.level, Question.created_at, QuestionUnit.unit_id)
            .join(
                QuestionUnit,
                and_(QuestionUnit.question_id == Question.id, QuestionUnit.user_id == self.user_id),
                isouter=True,
            )
            .where(
                Question.user_id == self.user_id, Question.status == "active", *self._not_skipped()
            )
        ).all()
        units: dict[uuid.UUID, set[uuid.UUID]] = {}
        info: dict[uuid.UUID, tuple[int, datetime]] = {}
        for question_id, level, created_at, unit_id in rows:
            info[question_id] = (level, created_at)
            units.setdefault(question_id, set())
            if unit_id is not None:
                units[question_id].add(unit_id)
        return {
            qid: LadderQuestion(qid, level, frozenset(units[qid]), created_at)
            for qid, (level, created_at) in info.items()
        }

    def scheduled_units(self) -> Sequence[DueUnit]:
        """Every (unit, core) with a schedule, due or not, and the question asked for it: the
        highest level the unit has earned (T5.2, domain.ladder), none when it has no question."""
        questions = list(self._ladder_questions().values())
        correct = self.correct_counts()
        rows = self.session.execute(
            select(MemoryState, KnowledgeUnit.subject_id)
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
                KnowledgeUnit.status == "active",
                KnowledgeUnit.skipped_at.is_(None),
                self._visible_subject(KnowledgeUnit.subject_id),  # type: ignore[arg-type]
            )
        ).all()
        by_unit: dict[uuid.UUID, list[LadderQuestion]] = {}
        for question in questions:
            for unit_id in question.unit_ids:
                by_unit.setdefault(unit_id, []).append(question)
        chosen = {
            row.unit_id: choose_for_unit(
                row.unit_id, by_unit.get(row.unit_id, ()), correct, self.ladder
            )
            for row, _ in rows
        }
        return [
            DueUnit(
                unit_id=row.unit_id,
                subject_id=subject_id,
                question_id=pick.question_id,
                state=State(
                    phase=Phase(row.phase),
                    step=row.step,
                    stability=row.stability,
                    difficulty=row.difficulty,
                    due=row.due,
                    last_review=row.last_review,
                ),
            )
            for row, subject_id in rows
            if (pick := chosen[row.unit_id]) is not None
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
        """Active questions of an eligible ladder level (T5.2) with a unit never asked and none
        skipped (a question of several units stays new while one of them has no schedule: T2.23
        fixes the old "none reviewed" rule, which left that unit never asked). A question linked to
        no unit counts as new, at level 1 only."""
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
                Question.id.in_(select(candidates.c.question_id)),
                *self._not_skipped(),
                self._visible_subject(Question.subject_id),  # type: ignore[arg-type]
            )
        ).all()
        ladder = self._ladder_questions()
        correct = self.correct_counts()
        return [
            NewQuestion(
                question_id=id,
                subject_id=subject_id,
                created_at=created_at,
                unasked_units=frozenset(unasked_units.get(id, ())),
            )
            for id, subject_id, created_at in rows
            # a level above the unit's waits; a question gone since the first read is left out
            if (found := ladder.get(id)) is not None and is_eligible(found, correct, self.ladder)
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
