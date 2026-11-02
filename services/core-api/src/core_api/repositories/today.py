"""What `compose_today` reads (T2.8, ARCH §5.3): every scheduled unit with the question that asks
about it, and every new question. Visible subjects only (not soft-deleted), active units and
questions only. One query each, whatever the number of units (US-03 AC2: under 300 ms)."""

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import ColumnElement, and_, exists, func, or_, select, text

from core_api.db.models import (
    KnowledgeUnit,
    MemoryState,
    Question,
    QuestionUnit,
    StudySession,
    Subject,
    Submission,
    UnitRevision,
)
from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
from core_api.domain.scheduling.fsrs_adapter import Phase
from core_api.domain.today import RECALL_LEVEL, DueUnit, NewQuestion
from core_api.domain.today_v2 import DraftSession
from core_api.repositories.base import UserScopedRepository

# Both while the status rename is in flight: a card saved by T7.8 is `canonical`, a legacy one is
# `active` (T7.11 migration 0031 renames the second and this shrinks to one value).
LIVE_STATUSES = ("canonical",)


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

    def _not_saved_today(self, day: date) -> ColumnElement[bool]:
        """A card saved today enters from the next learning day (US-02b AC12); one with no save
        day (seed, pipeline) is always eligible."""
        return or_(
            KnowledgeUnit.saved_learning_day.is_(None), KnowledgeUnit.saved_learning_day < day
        )

    def unasked_by_subject(self, *, day: date) -> dict[uuid.UUID, int]:
        """Units never asked, by visible subject: what the exam quota counts (T2.23, b2)."""
        scheduled = select(MemoryState.unit_id).where(
            MemoryState.user_id == self.user_id, MemoryState.facet == "core"
        )
        rows = self.session.execute(
            select(KnowledgeUnit.subject_id, func.count())
            .where(
                KnowledgeUnit.user_id == self.user_id,
                KnowledgeUnit.status.in_(LIVE_STATUSES),
                KnowledgeUnit.skipped_at.is_(None),
                KnowledgeUnit.id.not_in(scheduled),
                self._not_saved_today(day),
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
            .order_by(
                QuestionUnit.unit_id,
                func.coalesce(Question.unit_rev, 0).desc(),  # the question of the newest revision
                Question.created_at,
                Question.id,
            )
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
                KnowledgeUnit.status.in_(LIVE_STATUSES),
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
                KnowledgeUnit.status.in_(LIVE_STATUSES),
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

    def new_questions(self, *, day: date) -> Sequence[NewQuestion]:
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
                KnowledgeUnit.status.in_(LIVE_STATUSES),
                KnowledgeUnit.skipped_at.is_(None),
                KnowledgeUnit.id.not_in(scheduled),
                self._not_saved_today(day),
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
            select(
                Question.id,
                Question.subject_id,
                Question.created_at,
                func.coalesce(Question.unit_rev, 0),
            ).where(
                Question.user_id == self.user_id,
                Question.status == "active",
                Question.level == RECALL_LEVEL,
                Question.id.in_(select(candidates.c.question_id)),
                *self._not_skipped(),
                self._visible_subject(Question.subject_id),  # type: ignore[arg-type]
            )
        ).all()
        # A card with several review questions (the lazy one made after an edit does not retire
        # the old) is asked by its newest revision only; equal revisions all stay (T7.9).
        newest: dict[uuid.UUID, int] = {}
        rev_of = {id: rev for id, _, _, rev in rows}
        for id, units in unasked_units.items():
            for unit_id in units:
                newest[unit_id] = max(newest.get(unit_id, 0), rev_of.get(id, 0))
        return [
            NewQuestion(
                question_id=id,
                subject_id=subject_id,
                created_at=created_at,
                unasked_units=frozenset(unasked_units.get(id, ())),
            )
            for id, subject_id, created_at, rev in rows
            if not unasked_units.get(id) or any(rev >= newest[u] for u in unasked_units[id])
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

    def saved_on(self, day: date) -> bool:
        """Whether a card was saved on this learning day: it waits for the next one (AC12)."""
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        KnowledgeUnit.user_id == self.user_id,
                        KnowledgeUnit.saved_learning_day == day,
                        KnowledgeUnit.status.in_(LIVE_STATUSES),
                        self._visible_subject(KnowledgeUnit.subject_id),  # type: ignore[arg-type]
                    )
                )
            )
        )

    def unfinished_sessions(self) -> list[DraftSession]:
        """Study sessions of visible subjects with draft cards left or a submission waiting for
        the AI (`pending_ai`): one line each on Today, never a backlog count (US-03 AC1)."""
        drafts = (
            select(KnowledgeUnit.session_id, func.count().label("n"))
            .where(
                KnowledgeUnit.user_id == self.user_id,
                KnowledgeUnit.status == "draft",
                KnowledgeUnit.session_id.is_not(None),
            )
            .group_by(KnowledgeUnit.session_id)
            .subquery()
        )
        waiting = (
            select(Submission.session_id)
            .where(Submission.user_id == self.user_id, Submission.status == "pending_ai")
            .distinct()
            .subquery()
        )
        rows = self.session.execute(
            select(
                StudySession.id,
                StudySession.subject_id,
                StudySession.created_at,
                func.coalesce(drafts.c.n, 0),
                waiting.c.session_id.is_not(None),
            )
            .outerjoin(drafts, drafts.c.session_id == StudySession.id)
            .outerjoin(waiting, waiting.c.session_id == StudySession.id)
            .where(
                StudySession.user_id == self.user_id,
                self._visible_subject(StudySession.subject_id),  # type: ignore[arg-type]
                or_(drafts.c.n > 0, waiting.c.session_id.is_not(None)),
            )
        ).all()
        return [
            DraftSession(sid, subject, count, bool(pending), at)
            for sid, subject, at, count, pending in rows
        ]

    def stale_rev_units(self, question_ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
        """Canonical cards of these questions whose newest revision is later than the revision
        their review question was written from (a question from before revisions counts as 0):
        the condition of the lazy regeneration (T7.9 `ensure_review_question`, US-02b AC11)."""
        if not question_ids:
            return []
        links = self.session.execute(
            select(QuestionUnit.unit_id, func.max(func.coalesce(Question.unit_rev, 0)))
            .join(Question, Question.id == QuestionUnit.question_id)
            .join(KnowledgeUnit, KnowledgeUnit.id == QuestionUnit.unit_id)
            .where(
                QuestionUnit.user_id == self.user_id,
                Question.user_id == self.user_id,
                KnowledgeUnit.user_id == self.user_id,
                KnowledgeUnit.status == "canonical",
                KnowledgeUnit.retired_at.is_(None),
                Question.source == "review_auto",
                Question.status == "active",
                QuestionUnit.unit_id.in_(
                    select(QuestionUnit.unit_id).where(
                        QuestionUnit.user_id == self.user_id,
                        QuestionUnit.question_id.in_(question_ids),
                    )
                ),
            )
            .group_by(QuestionUnit.unit_id)
        ).all()
        have = {unit_id: rev for unit_id, rev in links}
        newest = {
            unit_id: rev
            for unit_id, rev in self.session.execute(
                select(UnitRevision.unit_id, func.max(UnitRevision.rev))
                .where(UnitRevision.user_id == self.user_id, UnitRevision.unit_id.in_(have))
                .group_by(UnitRevision.unit_id)
            )
        }
        return [u for u, rev in have.items() if u in newest and rev < newest[u]]

    def lazy_jobs_since(self, unit_ids: Sequence[uuid.UUID], since: datetime) -> set[uuid.UUID]:
        """Cards that already have a lazy review-question job of this user waiting or running, or
        deferred since `since` (the learning day's start), whatever became of it: one job per
        card per learning day, so a failed or empty one is not retried by every refetch of Today
        (plan review P1, the model budget)."""
        if not unit_ids:
            return set()
        rows = self.session.execute(
            text(
                "SELECT DISTINCT j.args->'payload'->>'unit_id' FROM procrastinate_jobs j"
                " WHERE j.task_name = 'regenerate_review_question'"
                " AND j.args->'payload'->>'user_id' = :user"
                " AND j.args->'payload'->>'unit_id' = ANY(:units)"
                " AND (j.status IN ('todo', 'doing') OR EXISTS ("
                "  SELECT 1 FROM procrastinate_events e"
                "  WHERE e.job_id = j.id AND e.type = 'deferred' AND e.at >= :since))"
            ),
            {"user": str(self.user_id), "units": [str(u) for u in unit_ids], "since": since},
        )
        return {uuid.UUID(row[0]) for row in rows}
