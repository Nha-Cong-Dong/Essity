"""Question types of a subject with their graded practice attempts (T8.6b, US-16 AC4-AC9).

Reads only. The attempts are the user's submitted practice attempts (no review session) with
their newest grade, oldest first: the same rows the schedule replays, so there is no score table.
"""

import uuid
from collections import defaultdict

from sqlalchemy import select

from core_api.db.models import Attempt, Grade, Question, QuestionType
from core_api.domain.mastery import PracticeVerdict, TypeAttempt
from core_api.repositories.base import UserScopedRepository


def _verdict(overall: str) -> PracticeVerdict:
    return "correct" if overall == "correct" else "partial" if overall == "partial" else "incorrect"


class PracticeTypeRepository(UserScopedRepository[QuestionType]):
    model = QuestionType

    def of_subject(self, subject_id: uuid.UUID) -> list[QuestionType]:
        query = (
            self._select().where(QuestionType.subject_id == subject_id).order_by(QuestionType.name)
        )
        return list(self.session.scalars(query))

    def attempts_by_type(self, subject_id: uuid.UUID) -> dict[uuid.UUID, list[TypeAttempt]]:
        latest = (
            select(Grade.attempt_id, Grade.overall)
            .where(Grade.user_id == self.user_id)
            .order_by(Grade.attempt_id, Grade.seq.desc())
            .distinct(Grade.attempt_id)
            .subquery()
        )
        query = (
            select(Question.type_id, latest.c.overall, Attempt.active_ms, Attempt.timing_ok)
            .join(Attempt, Attempt.question_id == Question.id)
            .join(latest, latest.c.attempt_id == Attempt.id)
            .where(
                Question.user_id == self.user_id,
                Question.subject_id == subject_id,
                Question.type_id.is_not(None),
                Attempt.user_id == self.user_id,
                Attempt.review_session_id.is_(None),
                Attempt.status == "submitted",
            )
            .order_by(Attempt.submitted_at, Attempt.id)
        )
        found: dict[uuid.UUID, list[TypeAttempt]] = defaultdict(list)
        for type_id, overall, active_ms, timing_ok in self.session.execute(query):
            seconds = active_ms / 1000 if active_ms is not None else None
            found[type_id].append(TypeAttempt(_verdict(overall), seconds, bool(timing_ok)))
        return found
