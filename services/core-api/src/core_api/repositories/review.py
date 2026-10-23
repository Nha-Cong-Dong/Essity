"""Repositories of review history (layer 3: added, never changed) and memory_state (layer 4).

The only writes besides adding are the two the triggers allow: closing a session once, and
editing an attempt while it is a draft. Both are an `UPDATE … WHERE` on that condition, so a
second close or an edit after submitting changes nothing and says so.
"""

import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from core_api.db.models import Attempt, Grade, GradeUnit, MemoryState, ReviewLog, ReviewSession
from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
from core_api.domain.scheduling.fsrs_adapter import Phase
from core_api.domain.scheduling.rating import ReviewRating, Verdict
from core_api.repositories.base import AppendOnlyRepository, UserScopedRepository
from core_api.repositories.question import (
    QuestionNotFoundError,
    QuestionRepository,
    QuestionUnitRepository,
)
from core_api.repositories.unit import KnowledgeUnitRepository, UnitNotFoundError


class ReviewSessionNotFoundError(LookupError):
    """No such review session for this user."""


class AttemptNotFoundError(LookupError):
    """No such attempt for this user."""


class AttemptNotDraftError(ValueError):
    """The attempt was submitted: it no longer changes."""


class AttemptNotSubmittedError(ValueError):
    """The attempt is still a draft: it can be graded only once submitted."""


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


class AttemptRepository(AppendOnlyRepository[Attempt]):
    model = Attempt

    def create_draft(self, review_session_id: uuid.UUID, question_id: uuid.UUID) -> Attempt:
        self._lock_open_session(review_session_id)
        if QuestionRepository(self.session, self.user_id).get(question_id) is None:
            raise QuestionNotFoundError(question_id)
        attempt = self.add(Attempt(review_session_id=review_session_id, question_id=question_id))
        self.session.flush()
        return attempt

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

    def _change_draft(self, id: uuid.UUID, **values: object) -> None:
        attempt = self.get(id)
        if attempt is None:
            raise AttemptNotFoundError(id)
        self._lock_open_session(attempt.review_session_id)
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


class MemoryStateRepository(UserScopedRepository[MemoryState]):
    """Layer 4: a cache of FSRS state, changed freely and rebuilt from review_log (T2.6)."""

    model = MemoryState

    def state(self, unit_id: uuid.UUID, facet: str = "core") -> State | None:
        """The FSRS state of (unit, facet), or None for a unit never reviewed."""
        row = self.session.scalars(
            self._select().where(MemoryState.unit_id == unit_id, MemoryState.facet == facet)
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
