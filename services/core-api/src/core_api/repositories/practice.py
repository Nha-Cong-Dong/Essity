"""Repositories of the practice schedule (T8.3, ADR-0029): `practice_log` (layer 3, added and
never changed) and `practice_state` (layer 4, a cache rebuilt from the log, like `memory_state`).

`practice_log` keeps the rating only, so the rebuild reads the *effective* log: the rows of each
attempt's latest grade (a regrade adds a row, it never changes an old one), oldest first. The
state's last verdict comes from the last effective rating. `removed_at` is not in the log: the
rebuild keeps the old row's.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from core_api.db.models import Grade, PracticeLog, Question, User
from core_api.db.models import PracticeState as PracticeStateRow
from core_api.domain.learning_day import day_bounds
from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.fsrs_adapter import MemoryState, Phase
from core_api.domain.scheduling.practice import PracticeState, replay_ratings, verdict_of
from core_api.repositories.base import AppendOnlyRepository, UserScopedRepository
from core_api.repositories.question import QuestionNotFoundError

REBUILD_BATCH = 1000
_MEMORY_FIELDS = ("phase", "step", "stability", "difficulty", "due", "last_review")


@dataclass(frozen=True)
class LoggedReview:
    """One effective row of a question's log."""

    question_id: uuid.UUID
    attempt_id: uuid.UUID
    rating: PracticeRating
    reviewed_at: datetime


class PracticeLogRepository(AppendOnlyRepository[PracticeLog]):
    model = PracticeLog

    def append(
        self,
        question_id: uuid.UUID,
        *,
        rating: PracticeRating,
        reviewed_at: datetime,
        grade_id: uuid.UUID,
    ) -> PracticeLog:
        log = self.add(
            PracticeLog(
                question_id=question_id,
                rating=int(rating),
                reviewed_at=reviewed_at,
                grade_id=grade_id,
            )
        )
        self.session.flush()
        return log

    def by_grade(self, grade_id: uuid.UUID) -> PracticeLog | None:
        return self.session.scalars(self._select().where(PracticeLog.grade_id == grade_id)).first()

    def effective(self, question_ids: Sequence[uuid.UUID] | None = None) -> list[LoggedReview]:
        """The rows that count, per question oldest first: the log rows of each attempt's latest
        grade (same rule as the card rebuild). One user's rows only, at every join."""
        latest = (
            select(Grade.id)
            .where(Grade.user_id == self.user_id)
            .order_by(Grade.attempt_id, Grade.seq.desc())
            .distinct(Grade.attempt_id)
            .subquery()
        )
        query = (
            select(
                PracticeLog.question_id,
                Grade.attempt_id,
                PracticeLog.rating,
                PracticeLog.reviewed_at,
            )
            .join(latest, latest.c.id == PracticeLog.grade_id)
            .join(Grade, (Grade.id == PracticeLog.grade_id) & (Grade.user_id == self.user_id))
            .where(PracticeLog.user_id == self.user_id)
            .order_by(PracticeLog.question_id, PracticeLog.reviewed_at, PracticeLog.seq)
        )
        if question_ids is not None:
            query = query.where(PracticeLog.question_id.in_(question_ids))
        return [
            LoggedReview(question_id, attempt_id, PracticeRating(rating), reviewed_at)
            for question_id, attempt_id, rating, reviewed_at in self.session.execute(query)
        ]


class PracticeStateRepository(UserScopedRepository[PracticeStateRow]):
    model = PracticeStateRow

    def hold_question(self, question_id: uuid.UUID) -> None:
        """Lock this user's question row until commit, so two writers of one question's schedule
        take turns, including the first attempt, when no state row exists yet to lock. FOR NO KEY
        UPDATE does not clash with the FOR KEY SHARE that the foreign keys take."""
        found = self.session.execute(
            select(Question.id)
            .where(Question.user_id == self.user_id, Question.id == question_id)
            .with_for_update(key_share=True)
        ).one_or_none()
        if found is None:
            raise QuestionNotFoundError(question_id)

    def row(self, question_id: uuid.UUID) -> PracticeStateRow | None:
        return self.session.scalars(
            self._select().where(PracticeStateRow.question_id == question_id),
            execution_options={"populate_existing": True},
        ).one_or_none()

    def state(self, question_id: uuid.UUID) -> PracticeState | None:
        """The schedule of a question, or None if it was never attempted. The last verdict is the
        last effective rating's, as the rebuild sets it."""
        row = self.row(question_id)
        if row is None:
            return None
        reviews = PracticeLogRepository(self.session, self.user_id).effective([question_id])
        assert reviews, "a practice_state row has a log behind it"
        return PracticeState(
            memory=MemoryState(
                phase=Phase(row.phase),
                step=row.step,
                stability=row.stability,
                difficulty=row.difficulty,
                due=row.due,
                last_review=row.last_review,
            ),
            last_verdict=verdict_of(reviews[-1].rating),
            removed_at=row.removed_at,
        )

    def set_removed_at(self, question_id: uuid.UUID, at: datetime | None) -> bool:
        """Stop (`at`) or resume (None) a question's schedule; False if it has no state yet."""
        changed = self.session.execute(
            update(PracticeStateRow)
            .where(
                PracticeStateRow.user_id == self.user_id,
                PracticeStateRow.question_id == question_id,
            )
            .values(removed_at=at)
            .returning(PracticeStateRow.id)
            .execution_options(synchronize_session="fetch")
        ).first()
        return changed is not None

    def due_on(self, day: date) -> Sequence[PracticeStateRow]:
        """Questions due by the end of learning day `day` in the user's own time zone and day
        start; a removed question is never due (`practice.is_due`, in SQL)."""
        user = self.session.get(User, self.user_id)
        assert user is not None
        _, end = day_bounds(day, ZoneInfo(user.timezone), user.day_start_hour)
        query = (
            self._select()
            .where(PracticeStateRow.removed_at.is_(None), PracticeStateRow.due < end)
            .order_by(PracticeStateRow.due)
        )
        return self.session.scalars(query).all()

    def rebuild(self, question_ids: Sequence[uuid.UUID] | None = None) -> int:
        """Rebuild the cache from the effective log, for some questions or all of this user's:
        drop the rows (keeping each `removed_at`), replay every question's ratings through the
        step the live path uses, insert again. Returns the number of states written."""
        # Take the question locks first, in id order, so a remove or a recording waits for this
        # rebuild and then finds the new rows (without them its UPDATE would see the deleted ones).
        held = select(Question.id).where(
            Question.user_id == self.user_id,
            Question.id.in_(
                select(PracticeLog.question_id).where(PracticeLog.user_id == self.user_id)
            ),
        )
        if question_ids is not None:
            held = held.where(Question.id.in_(question_ids))
        self.session.execute(held.order_by(Question.id).with_for_update(key_share=True)).all()
        drop = delete(PracticeStateRow).where(PracticeStateRow.user_id == self.user_id)
        if question_ids is not None:
            drop = drop.where(PracticeStateRow.question_id.in_(question_ids))
        removed = {
            question_id: removed_at
            for question_id, removed_at in self.session.execute(
                drop.returning(PracticeStateRow.question_id, PracticeStateRow.removed_at)
            )
        }
        by_question: dict[uuid.UUID, list[LoggedReview]] = {}
        for review in PracticeLogRepository(self.session, self.user_id).effective(question_ids):
            by_question.setdefault(review.question_id, []).append(review)
        rows: list[dict[str, object]] = []
        for question_id, reviews in by_question.items():
            state = replay_ratings((r.rating, r.reviewed_at) for r in reviews)
            assert state is not None
            memory = state.memory
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": self.user_id,
                    "question_id": question_id,
                    "phase": memory.phase.value,
                    "step": memory.step,
                    "stability": memory.stability,
                    "difficulty": memory.difficulty,
                    "due": memory.due,
                    "last_review": memory.last_review,
                    "removed_at": removed.get(question_id),
                }
            )
        # An upsert, not a plain insert: a writer without the question lock (a whole-user CLI
        # rebuild) may have added the row meanwhile. `removed_at` stays out of `set_`: the rebuild
        # never overwrites what remove/readd wrote since.
        for start in range(0, len(rows), REBUILD_BATCH):
            statement = insert(PracticeStateRow).values(rows[start : start + REBUILD_BATCH])
            excluded = statement.excluded
            self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=["user_id", "question_id"],
                    set_={name: getattr(excluded, name) for name in _MEMORY_FIELDS},
                )
            )
        self.session.expire_all()
        return len(rows)
