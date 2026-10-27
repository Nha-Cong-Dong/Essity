"""Repositories of review history (layer 3: added, never changed) and memory_state (layer 4).

The only writes besides adding are the two the triggers allow: closing a session once, and
editing an attempt while it is a draft. Both are an `UPDATE … WHERE` on that condition, so a
second close or an edit after submitting changes nothing and says so.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from itertools import groupby
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from core_api.db.models import (
    Attempt,
    Exam,
    Grade,
    GradeUnit,
    KnowledgeUnit,
    MemoryState,
    Question,
    QuestionUnit,
    ReviewLog,
    ReviewSession,
    ReviewSessionItem,
    Subject,
    User,
)
from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
from core_api.domain.scheduling.fsrs_adapter import Phase
from core_api.domain.scheduling.rating import ReviewRating, Verdict
from core_api.domain.scheduling.replay import replay
from core_api.domain.today import MAX_QUESTIONS
from core_api.repositories.base import AppendOnlyRepository, UserScopedRepository
from core_api.repositories.question import (
    QuestionNotFoundError,
    QuestionRepository,
    QuestionUnitRepository,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository, UnitNotFoundError


class ReviewSessionNotFoundError(LookupError):
    """No such review session for this user."""


class AttemptNotFoundError(LookupError):
    """No such attempt for this user."""


class AttemptNotDraftError(ValueError):
    """The attempt was submitted: it no longer changes."""


class AttemptNotSubmittedError(ValueError):
    """The attempt is still a draft: it can be graded only once submitted."""


class QuestionNotAskableError(ValueError):
    """The attempt's question can no longer be asked in its session (skipped unit, T2.23)."""


class ReviewSessionEndedError(ValueError):
    """The session has ended: its answers no longer change (plan D14)."""


class UnitsMismatchError(ValueError):
    """A grade must judge exactly the units its question checks."""


class ReviewSessionRepository(AppendOnlyRepository[ReviewSession]):
    model = ReviewSession

    def start(self, learning_day: date, started_at: datetime) -> ReviewSession:
        session = self.add(ReviewSession(learning_day=learning_day, started_at=started_at))
        self.session.flush()
        return session

    def open_for_day(
        self, learning_day: date, now: datetime, subject_id: uuid.UUID | None = None
    ) -> tuple[ReviewSession, bool]:
        """The open session of `learning_day`, made if there is none: (session, made now). Two
        tabs pressing "Bắt đầu" at once get the same one (plan C4): the partial unique index
        refuses the second insert, which then reads the first once it has committed."""
        made = self.session.execute(
            insert(ReviewSession)
            .values(
                id=uuid.uuid4(),
                user_id=self.user_id,
                learning_day=learning_day,
                started_at=now,
                subject_id=subject_id,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "learning_day"],
                index_where=ReviewSession.ended_at.is_(None),
            )
            .returning(ReviewSession.id)
        ).scalar_one_or_none()
        found = self.open_on(learning_day)
        assert found is not None
        return found, made is not None

    def hold_for_update(self, id: uuid.UUID) -> ReviewSession | None:
        """The session, locked FOR UPDATE until commit: a submit holds it FOR SHARE, so stopping
        waits for one in flight and then counts it (plan D14)."""
        return self.session.scalars(
            self._select().where(ReviewSession.id == id).with_for_update()
        ).one_or_none()

    def open_on(self, learning_day: date) -> ReviewSession | None:
        """The session still open on `learning_day`, if any."""
        query = self._select().where(
            ReviewSession.learning_day == learning_day, ReviewSession.ended_at.is_(None)
        )
        return self.session.scalars(query).one_or_none()

    def end(self, id: uuid.UUID, ended_at: datetime, *, reason: str) -> bool:
        """Close the session once; False when it is not this user's or is already closed."""
        closed = self.session.execute(
            update(ReviewSession)
            .where(
                ReviewSession.user_id == self.user_id,
                ReviewSession.id == id,
                ReviewSession.ended_at.is_(None),
            )
            .values(ended_at=ended_at, stop_reason=reason)
            .returning(ReviewSession.id)
        ).first()
        return closed is not None


@dataclass(frozen=True)
class SessionStep:
    question: Question
    subject: Subject
    attempt: Attempt | None
    askable: bool

    @property
    def answered(self) -> bool:
        return self.attempt is not None and self.attempt.status == "submitted"


def session_counts(steps: Sequence[SessionStep]) -> tuple[int, int]:
    """(answered, total) of a session: what can no longer be asked (a deleted subject, a retired
    question) drops out of the total unless it was already answered."""
    answered = sum(step.answered for step in steps)
    return answered, answered + sum(step.askable and not step.answered for step in steps)


class ReviewSessionItemRepository(AppendOnlyRepository[ReviewSessionItem]):
    """The questions of a session, in order (T2.9 plan C1); added once, when it starts."""

    model = ReviewSessionItem

    def add_all(
        self, review_session_id: uuid.UUID, question_ids: Sequence[uuid.UUID]
    ) -> list[ReviewSessionItem]:
        items = [
            self.add(
                ReviewSessionItem(
                    review_session_id=review_session_id, position=n, question_id=question_id
                )
            )
            for n, question_id in enumerate(question_ids, start=1)
        ]
        self.session.flush()
        return items

    def append(
        self, review_session_id: uuid.UUID, question_ids: Sequence[uuid.UUID]
    ) -> list[ReviewSessionItem]:
        """Questions that take the place of skipped ones (T2.23), after the last item. Only the
        holder of the session's FOR UPDATE lock calls this."""
        last = self.session.scalar(
            select(func.max(ReviewSessionItem.position)).where(
                ReviewSessionItem.user_id == self.user_id,
                ReviewSessionItem.review_session_id == review_session_id,
            )
        )
        items = [
            self.add(
                ReviewSessionItem(
                    review_session_id=review_session_id, position=n, question_id=question_id
                )
            )
            for n, question_id in enumerate(question_ids, start=(last or 0) + 1)
        ]
        self.session.flush()
        return items

    def progress(self, review_session_id: uuid.UUID) -> list[SessionStep]:
        """Each item of the session in order, with its question, its subject, whether it can
        still be asked (question active, subject not deleted, no unit of it skipped, and the
        session's cap of `MAX_QUESTIONS` not passed) and its attempt, if any. The cap counts the
        answered questions first, then the unanswered ones in order, so a skip undone after a
        replacement was added hides the last replacement instead of making a 21st question."""
        skipped = (
            select(QuestionUnit.question_id)
            .join(
                KnowledgeUnit,
                (KnowledgeUnit.id == QuestionUnit.unit_id)
                & (KnowledgeUnit.user_id == self.user_id),
            )
            .where(QuestionUnit.user_id == self.user_id, KnowledgeUnit.skipped_at.is_not(None))
        )
        skipped_ids = set(self.session.scalars(skipped))
        rows = self.session.execute(
            select(ReviewSessionItem, Question, Subject, Attempt)
            .join(
                Question,
                (Question.id == ReviewSessionItem.question_id) & (Question.user_id == self.user_id),
            )
            .join(
                Subject,
                (Subject.id == Question.subject_id) & (Subject.user_id == self.user_id),
            )
            .outerjoin(
                Attempt,
                (Attempt.review_session_id == ReviewSessionItem.review_session_id)
                & (Attempt.question_id == ReviewSessionItem.question_id)
                & (Attempt.user_id == self.user_id),
            )
            .where(
                ReviewSessionItem.user_id == self.user_id,
                ReviewSessionItem.review_session_id == review_session_id,
            )
            .order_by(ReviewSessionItem.position)
        ).all()
        steps = [
            SessionStep(
                question=question,
                subject=subject,
                attempt=attempt,
                askable=question.status == "active"
                and subject.deleted_at is None
                and question.id not in skipped_ids,
            )
            for _, question, subject, attempt in rows
        ]
        places = MAX_QUESTIONS - sum(step.answered for step in steps)
        capped: list[SessionStep] = []
        for step in steps:
            if step.askable and not step.answered:
                places -= 1
                if places < 0:
                    step = replace(step, askable=False)
            capped.append(step)
        return capped

    def of_session(self, review_session_id: uuid.UUID) -> Sequence[ReviewSessionItem]:
        query = (
            self._select()
            .where(ReviewSessionItem.review_session_id == review_session_id)
            .order_by(ReviewSessionItem.position)
        )
        return self.session.scalars(query).all()


class AttemptRepository(AppendOnlyRepository[Attempt]):
    model = Attempt

    def create_draft(self, review_session_id: uuid.UUID, question_id: uuid.UUID) -> Attempt:
        """The draft of this question in this session: `open_draft` without saying who made it."""
        return self.open_draft(review_session_id, question_id)[0]

    def open_draft(
        self, review_session_id: uuid.UUID, question_id: uuid.UUID
    ) -> tuple[Attempt, bool]:
        """The draft of this question in this session, made if there is none: (attempt, made now).
        Locks in this order: the session, then the question's subject (FOR SHARE, so a soft delete
        waits for this draft or this finds the subject gone: T2.3b plan F3), then the attempt.
        Two tabs opening the same question at once (T2.15 (c)): the second insert waits on
        UNIQUE(review_session_id, question_id), then reads the first draft instead of failing.
        Saving and submitting need no subject lock: a subject with an attempt cannot be
        soft-deleted (that path comes with T6.3)."""
        self._lock_open_session(review_session_id)
        question = QuestionRepository(self.session, self.user_id).get(question_id)
        if question is None:
            raise QuestionNotFoundError(question_id)
        SubjectRepository(self.session, self.user_id).hold_for_share(question.subject_id)
        self._check_askable(review_session_id, question_id)
        made = self.session.execute(
            insert(Attempt)
            .values(
                id=uuid.uuid4(),
                user_id=self.user_id,
                review_session_id=review_session_id,
                question_id=question_id,
            )
            .on_conflict_do_nothing(index_elements=["review_session_id", "question_id"])
            .returning(Attempt.id)
        ).scalar_one_or_none()
        found = self.session.scalars(
            self._select().where(
                Attempt.review_session_id == review_session_id, Attempt.question_id == question_id
            )
        ).one()
        return found, made is not None

    def save_draft(self, id: uuid.UUID, *, answer_text: str, dont_remember: bool) -> None:
        self._change_draft(id, answer_text=answer_text, dont_remember=dont_remember)

    def submit(self, id: uuid.UUID, submitted_at: datetime) -> None:
        self._change_draft(id, status="submitted", submitted_at=submitted_at)

    def _lock_open_session(self, review_session_id: uuid.UUID) -> None:
        """Hold the session row FOR SHARE until commit, so `end` waits for this write or this
        write sees the session ended (plan D14); the FOR KEY SHARE of the foreign key alone does
        not stop `end`. Anything that later touches attempts while ending a session (T2.9) must
        lock the session first, then the attempts."""
        ended_at = self.session.execute(
            select(ReviewSession.ended_at)
            .where(ReviewSession.user_id == self.user_id, ReviewSession.id == review_session_id)
            .with_for_update(read=True)
        ).one_or_none()
        if ended_at is None:
            raise ReviewSessionNotFoundError(review_session_id)
        if ended_at[0] is not None:
            raise ReviewSessionEndedError(review_session_id)

    def _check_askable(self, review_session_id: uuid.UUID, question_id: uuid.UUID) -> None:
        """Called after the session lock: a skip that committed before it shows here (T2.23)."""
        steps = ReviewSessionItemRepository(self.session, self.user_id).progress(review_session_id)
        if any(not step.askable and step.question.id == question_id for step in steps):
            raise QuestionNotAskableError(question_id)

    def _change_draft(self, id: uuid.UUID, **values: object) -> None:
        attempt = self.get(id)
        if attempt is None:
            raise AttemptNotFoundError(id)
        self._lock_open_session(attempt.review_session_id)
        if attempt.status == "draft":
            self._check_askable(attempt.review_session_id, attempt.question_id)
        changed = self.session.execute(
            update(Attempt)
            .where(Attempt.user_id == self.user_id, Attempt.id == id, Attempt.status == "draft")
            .values(**values)
            .returning(Attempt.id)
            .execution_options(synchronize_session="fetch")
        ).first()
        if changed is None:
            raise AttemptNotDraftError(id)


class GradeRepository(AppendOnlyRepository[Grade]):
    model = Grade

    def add_with_units(
        self,
        attempt_id: uuid.UUID,
        *,
        source: str,
        overall: Verdict,
        understanding: int | None,
        units: Mapping[uuid.UUID, Verdict],
        run_id: uuid.UUID | None,
        missing: Sequence[str] = (),
        anchors_used: Sequence[str] = (),
    ) -> Grade:
        """A new judgement of the attempt, with one verdict per unit (us-05 AC9)."""
        attempt = AttemptRepository(self.session, self.user_id).get(attempt_id)
        if attempt is None:
            raise AttemptNotFoundError(attempt_id)
        if attempt.status != "submitted":
            raise AttemptNotSubmittedError(attempt_id)
        checked = QuestionUnitRepository(self.session, self.user_id).units_of(attempt.question_id)
        if set(units) != {unit.id for unit in checked}:
            raise UnitsMismatchError(attempt_id)
        grade = self.add(
            Grade(
                attempt_id=attempt_id,
                source=source,
                overall=overall.value,
                understanding=understanding,
                missing=list(missing),
                anchors_used=list(anchors_used),
                run_id=run_id,
            )
        )
        self.session.flush()
        for unit_id, verdict in units.items():
            self.session.add(
                GradeUnit(
                    user_id=self.user_id, grade_id=grade.id, unit_id=unit_id, verdict=verdict.value
                )
            )
        self.session.flush()
        return grade

    def try_lock_attempt(self, attempt_id: uuid.UUID) -> bool:
        """Take the attempt's grading lock for this transaction, or say someone holds it (T2.13
        plan D-2): one grading at a time, without a row lock held while the AI answers. The key
        is a 64-bit hash of the id in a namespace of its own; a collision only gives a false
        "in progress". Check the attempt is this user's first: otherwise anyone knowing an id
        could hold a victim's lock (plan 🟡16)."""
        return bool(
            self.session.scalar(
                select(
                    func.pg_try_advisory_xact_lock(
                        func.hashtextextended(str(attempt_id), GRADING_LOCK_NAMESPACE)
                    )
                )
            )
        )

    def is_being_graded(self, attempt_id: uuid.UUID) -> bool:
        """Whether another transaction holds the attempt's grading lock, read from pg_locks
        without taking it (plan 🟡9): a read taking it could make a submit arriving at that
        moment answer "in progress" with nobody grading."""
        key = func.hashtextextended(str(attempt_id), GRADING_LOCK_NAMESPACE)
        held = text(
            "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory'"
            " AND objsubid = 1 AND ((classid::bigint << 32) | objid::bigint) = :key"
            " AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
            " AND pid <> pg_backend_pid())"
        )
        value = self.session.scalar(select(key))
        return bool(self.session.scalar(held, {"key": value}))

    def graded(self, attempt_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """Which of these attempts have a grade (plan D-7: the others are offered "Chấm lại")."""
        if not attempt_ids:
            return set()
        query = select(Grade.attempt_id).where(
            Grade.user_id == self.user_id, Grade.attempt_id.in_(attempt_ids)
        )
        return set(self.session.scalars(query))

    def unit_verdicts(self, grade_id: uuid.UUID) -> dict[uuid.UUID, str]:
        """A grade's verdict on each unit it judged (US-05 AC9)."""
        rows = self.session.execute(
            select(GradeUnit.unit_id, GradeUnit.verdict).where(
                GradeUnit.user_id == self.user_id, GradeUnit.grade_id == grade_id
            )
        ).all()
        return {unit_id: verdict for unit_id, verdict in rows}

    def latest_for_attempt(self, attempt_id: uuid.UUID) -> Grade | None:
        """The attempt's current judgement: its newest grade (plan D2)."""
        query = self._select().where(Grade.attempt_id == attempt_id).order_by(Grade.seq.desc())
        return self.session.scalars(query.limit(1)).first()


class ReviewLogRepository(AppendOnlyRepository[ReviewLog]):
    model = ReviewLog

    def append(
        self,
        unit_id: uuid.UUID,
        *,
        rating: ReviewRating,
        reviewed_at: datetime,
        grade_id: uuid.UUID,
        facet: str = "core",
    ) -> ReviewLog:
        log = self.add(
            ReviewLog(
                unit_id=unit_id,
                facet=facet,
                rating=int(rating),
                reviewed_at=reviewed_at,
                grade_id=grade_id,
            )
        )
        self.session.flush()
        return log


REBUILD_BATCH = 1000
GRADING_LOCK_NAMESPACE = 7213  # T2.13: advisory locks on attempts being graded
_STATE_FIELDS = ("phase", "step", "stability", "difficulty", "due", "last_review")


class MemoryStateRepository(UserScopedRepository[MemoryState]):
    """Layer 4: a cache of FSRS state, changed freely and rebuilt from review_log (T2.6)."""

    model = MemoryState

    def state(self, unit_id: uuid.UUID, facet: str = "core") -> State | None:
        """The FSRS state of (unit, facet), or None for a unit never reviewed."""
        row = self.session.scalars(
            self._select().where(MemoryState.unit_id == unit_id, MemoryState.facet == facet),
            # A fresh read, not the object an earlier statement left in the session (T2.13
            # reads it after locking the unit; plan 🟡12).
            execution_options={"populate_existing": True},
        ).one_or_none()
        if row is None:
            return None
        return State(
            phase=Phase(row.phase),
            step=row.step,
            stability=row.stability,
            difficulty=row.difficulty,
            due=row.due,
            last_review=row.last_review,
        )

    def upsert(self, unit_id: uuid.UUID, facet: str, state: State) -> MemoryState:
        if KnowledgeUnitRepository(self.session, self.user_id).get(unit_id) is None:
            raise UnitNotFoundError(unit_id)
        values = {
            "phase": state.phase.value,
            "step": state.step,
            "stability": state.stability,
            "difficulty": state.difficulty,
            "due": state.due,
            "last_review": state.last_review,
        }
        statement = (
            insert(MemoryState)
            .values(id=uuid.uuid4(), user_id=self.user_id, unit_id=unit_id, facet=facet, **values)
            .on_conflict_do_update(index_elements=["user_id", "unit_id", "facet"], set_=values)
            .returning(MemoryState)
        )
        return self.session.scalars(statement, execution_options={"populate_existing": True}).one()

    def due_until(self, until: datetime) -> Sequence[MemoryState]:
        query = self._select().where(MemoryState.due <= until).order_by(MemoryState.due)
        return self.session.scalars(query).all()

    def delete_all(self) -> int:
        """Drop this user's cache before rebuilding it from review_log (T2.6)."""
        deleted = self.session.execute(
            delete(MemoryState).where(MemoryState.user_id == self.user_id)
        )
        return deleted.rowcount  # type: ignore[attr-defined]

    def rebuild(
        self, subject_id: uuid.UUID | None = None, unit_ids: Sequence[uuid.UUID] | None = None
    ) -> int:
        """Rebuild the cache from review_log (T2.6), for one subject or all of them: drop it,
        then replay each (unit, facet) through `schedule_review` with its subject's exam date
        as it is now. A moved exam reaches the schedule this way (US-01 AC3). Returns the number
        of states written."""
        user = self.session.get(User, self.user_id)
        assert user is not None
        tz = ZoneInfo(user.timezone)
        units = select(KnowledgeUnit.id).where(KnowledgeUnit.user_id == self.user_id)
        if subject_id is not None:
            units = units.where(KnowledgeUnit.subject_id == subject_id)
        if unit_ids is not None:  # T2.13: only the units an older answer touches
            units = units.where(KnowledgeUnit.id.in_(unit_ids))
        self.session.execute(
            delete(MemoryState).where(
                MemoryState.user_id == self.user_id, MemoryState.unit_id.in_(units)
            )
        )
        rows: list[dict[str, object]] = []
        for (unit_id, facet, exam_day), reviews in groupby(
            self._current_reviews(subject_id, unit_ids),
            key=lambda row: (row[0], row[1], row[4]),
        ):
            state = replay(
                ((ReviewRating(row[2]), row[3]) for row in reviews),
                exam_day=exam_day,
                tz=tz,
                day_start_hour=user.day_start_hour,
            )
            assert state is not None
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": self.user_id,
                    "unit_id": unit_id,
                    "facet": facet,
                    "phase": state.phase.value,
                    "step": state.step,
                    "stability": state.stability,
                    "difficulty": state.difficulty,
                    "due": state.due,
                    "last_review": state.last_review,
                }
            )
        # One insert, not one upsert per unit: the rows were just deleted, and every unit comes
        # from this user's own review_log joined to knowledge_unit (rebuild at real size, #20).
        # One upsert per batch, not per unit: a review written meanwhile (T2.13, or a CLI
        # rebuild) updates the row instead of failing the rebuild on the unique key. Batches keep
        # each statement under Postgres's 65 535 parameters (10 a row; review final #21).
        for start in range(0, len(rows), REBUILD_BATCH):
            statement = insert(MemoryState).values(rows[start : start + REBUILD_BATCH])
            excluded = statement.excluded
            self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=["user_id", "unit_id", "facet"],
                    set_={name: getattr(excluded, name) for name in _STATE_FIELDS},
                )
            )
        self.session.expire_all()
        return len(rows)

    def _current_reviews(
        self, subject_id: uuid.UUID | None, unit_ids: Sequence[uuid.UUID] | None = None
    ) -> Sequence[tuple[uuid.UUID, str, int, datetime, date]]:
        """(unit, facet, rating, reviewed_at, exam date) of every review that counts: the rows of
        each attempt's latest grade (plan D7), in the order they happened."""
        # Each attempt's latest grade, computed once as a set, then joined: a per-row MAX(seq)
        # subquery ran once per grade per unit and grew with the square of the history.
        latest = (
            select(Grade.id)
            .where(Grade.user_id == self.user_id)
            .order_by(Grade.attempt_id, Grade.seq.desc())
            .distinct(Grade.attempt_id)
            .subquery()
        )
        query = (
            select(
                ReviewLog.unit_id,
                ReviewLog.facet,
                ReviewLog.rating,
                ReviewLog.reviewed_at,
                Exam.exam_date,
            )
            .join(latest, latest.c.id == ReviewLog.grade_id)
            .join(
                KnowledgeUnit,
                (KnowledgeUnit.id == ReviewLog.unit_id) & (KnowledgeUnit.user_id == self.user_id),
            )
            .join(
                Exam,
                (Exam.subject_id == KnowledgeUnit.subject_id) & (Exam.user_id == self.user_id),
            )
            .where(ReviewLog.user_id == self.user_id)
            .order_by(ReviewLog.unit_id, ReviewLog.facet, ReviewLog.reviewed_at, ReviewLog.seq)
        )
        if subject_id is not None:
            query = query.where(KnowledgeUnit.subject_id == subject_id)
        if unit_ids is not None:
            query = query.where(ReviewLog.unit_id.in_(unit_ids))
        return [tuple(row) for row in self.session.execute(query)]  # type: ignore[misc]
