"""Practice attempts (T8.4, US-16): attempts at a question outside any review session.

A practice attempt is `attempt.review_session_id IS NULL`. This repository sees only those: a review
attempt is invisible here, as a practice attempt is to `AttemptRepository` (404 both ways). Opening
a question is idempotent (migration 0029: one open draft per user and question) and writes
`served_at` once, with the server's clock. The submit is one UPDATE that also freezes the timing.
"""

import uuid
from datetime import datetime

from sqlalchemy import Select, select, text, update
from sqlalchemy.dialects.postgresql import insert

from core_api.db.models import Attempt, Question
from core_api.domain.practice_attempt import practice_timing
from core_api.repositories.base import AppendOnlyRepository
from core_api.repositories.question import QuestionNotFoundError
from core_api.repositories.review import AttemptNotDraftError, AttemptNotFoundError
from core_api.repositories.subject import SubjectRepository

__all__ = [
    "AttemptNotDraftError",
    "AttemptNotFoundError",
    "DraftContendedError",
    "PracticeAttemptRepository",
    "QuestionNotFoundError",
]

OPEN_TRIES = 3
DRAFT_INDEX_WHERE = text("review_session_id IS NULL AND status = 'draft'")


class DraftContendedError(Exception):
    """Other tabs keep submitting the draft as fast as we open it: give up after `OPEN_TRIES`."""


class PracticeAttemptRepository(AppendOnlyRepository[Attempt]):
    model = Attempt

    def _select(self) -> Select[tuple[Attempt]]:
        return super()._select().where(Attempt.review_session_id.is_(None))

    def get_practice(self, id: uuid.UUID) -> Attempt | None:
        return self.get(id)

    def open_draft(self, question_id: uuid.UUID, now: datetime) -> tuple[Attempt, bool]:
        """The open draft of this question, made if there is none: (attempt, made now).
        `served_at` is the server's `now` at the first serve and is never overwritten. Two tabs
        opening one question at once: the second insert waits on the partial unique index, does
        nothing, and then reads the first draft."""
        question = self.session.execute(
            select(Question.subject_id).where(
                Question.user_id == self.user_id,
                Question.id == question_id,
                Question.status == "active",
            )
        ).one_or_none()
        if question is None:
            raise QuestionNotFoundError(question_id)
        SubjectRepository(self.session, self.user_id).hold_for_share(question.subject_id)
        for _ in range(OPEN_TRIES):
            made = self.session.execute(
                insert(Attempt)
                .values(
                    id=uuid.uuid4(),
                    user_id=self.user_id,
                    review_session_id=None,
                    question_id=question_id,
                    served_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "question_id"], index_where=DRAFT_INDEX_WHERE
                )
                .returning(Attempt.id)
            ).scalar_one_or_none()
            found = self._open_one(question_id)
            if found is not None:
                return found, made is not None
            # the other tab submitted between our insert and read: insert again (bounded)
        raise DraftContendedError(question_id)

    def _open_one(self, question_id: uuid.UUID) -> Attempt | None:
        return self.session.scalars(
            self._select().where(Attempt.question_id == question_id, Attempt.status == "draft"),
            execution_options={"populate_existing": True},
        ).one_or_none()

    def save_draft(self, id: uuid.UUID, *, answer_text: str, dont_remember: bool) -> None:
        self._change_draft(id, answer_text=answer_text, dont_remember=dont_remember)

    def submit(
        self,
        id: uuid.UUID,
        submitted_at: datetime,
        *,
        hidden_ms: int,
        reference_seconds: float,
        answer_text: str | None = None,
        dont_remember: bool | None = None,
    ) -> Attempt:
        """Submit: one UPDATE writes status, `submitted_at` and the three timing columns, which
        the guard then freezes. The row is read FOR UPDATE first, so a double submit makes the
        second raise `AttemptNotDraftError` and the first timing stands."""
        attempt = self.session.scalars(
            self._select().where(Attempt.id == id).with_for_update(),
            execution_options={"populate_existing": True},
        ).one_or_none()
        if attempt is None:
            raise AttemptNotFoundError(id)
        if attempt.status != "draft":
            raise AttemptNotDraftError(id)
        assert attempt.served_at is not None  # CHECK practice_has_served_at
        timing = practice_timing(attempt.served_at, submitted_at, hidden_ms, reference_seconds)
        values: dict[str, object] = {
            "status": "submitted",
            "submitted_at": submitted_at,
            "hidden_ms": timing.hidden_ms,
            "active_ms": timing.active_ms,
            "timing_ok": timing.timing_ok,
        }
        if answer_text is not None:
            values["answer_text"] = answer_text
        if dont_remember is not None:
            values["dont_remember"] = dont_remember
        self.session.execute(
            update(Attempt)
            .where(Attempt.user_id == self.user_id, Attempt.id == id, Attempt.status == "draft")
            .values(**values)
            .execution_options(synchronize_session="fetch")
        )
        self.session.refresh(attempt)
        return attempt

    def _change_draft(self, id: uuid.UUID, **values: object) -> None:
        changed = self.session.execute(
            update(Attempt)
            .where(
                Attempt.user_id == self.user_id,
                Attempt.id == id,
                Attempt.review_session_id.is_(None),
                Attempt.status == "draft",
            )
            .values(**values)
            .returning(Attempt.id)
            .execution_options(synchronize_session="fetch")
        ).first()
        if changed is None:
            if self.get(id) is None:
                raise AttemptNotFoundError(id)
            raise AttemptNotDraftError(id)
