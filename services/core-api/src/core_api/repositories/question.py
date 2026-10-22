import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from core_api.db.models import KnowledgeUnit, Question, QuestionUnit
from core_api.domain.question_hash import content_hash
from core_api.repositories.base import UserScopedRepository
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository, UnitNotFoundError


class QuestionNotFoundError(LookupError):
    """No such question for this user."""


class QuestionConflictError(ValueError):
    """The subject already has this question with another level, answer or rubric: adding it
    again would keep the old one in silence (review 8a92b17). Retire and re-add instead."""


class SubjectMismatchError(ValueError):
    """A question and a unit of different subjects (plan D9)."""


class QuestionRepository(UserScopedRepository[Question]):
    model = Question

    def add_idempotent(
        self,
        subject_id: uuid.UUID,
        *,
        level: int,
        prompt: str,
        reference_answer: str,
        run_id: uuid.UUID,
        rubric: Any | None = None,
    ) -> Question:
        """This question of the subject, added once: the same prompt again (however typed)
        returns the existing row instead of a second one, never nothing (plan D12)."""
        if SubjectRepository(self.session, self.user_id).get(subject_id) is None:
            raise SubjectNotFoundError(subject_id)
        digest = content_hash(prompt)
        self.session.flush()
        statement = (
            insert(Question)
            .values(
                id=uuid.uuid4(),
                user_id=self.user_id,
                subject_id=subject_id,
                level=level,
                prompt=prompt,
                reference_answer=reference_answer,
                rubric=rubric,
                status="active",
                content_hash=digest,
                run_id=run_id,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "subject_id", "content_hash"])
        )
        self.session.execute(statement)
        # The row just added, or the one already there: one per user, subject and hash.
        question = self.session.scalars(
            self._select().where(Question.subject_id == subject_id, Question.content_hash == digest)
        ).one()
        if (question.level, question.reference_answer, question.rubric) != (
            level,
            reference_answer,
            rubric,
        ):
            raise QuestionConflictError(question.id)
        return question


class QuestionUnitRepository(UserScopedRepository[QuestionUnit]):
    model = QuestionUnit

    def link(self, question_id: uuid.UUID, unit_id: uuid.UUID) -> QuestionUnit:
        question = QuestionRepository(self.session, self.user_id).get(question_id)
        if question is None:
            raise QuestionNotFoundError(question_id)
        unit = KnowledgeUnitRepository(self.session, self.user_id).get(unit_id)
        if unit is None:
            raise UnitNotFoundError(unit_id)
        if unit.subject_id != question.subject_id:
            raise SubjectMismatchError(question_id, unit_id)
        link = self.add(
            QuestionUnit(subject_id=question.subject_id, question_id=question_id, unit_id=unit_id)
        )
        self.session.flush()
        return link

    def units_of(self, question_id: uuid.UUID) -> Sequence[KnowledgeUnit]:
        units = KnowledgeUnitRepository(self.session, self.user_id)
        query = units._select().where(  # pyright: ignore[reportPrivateUsage]
            KnowledgeUnit.id.in_(
                self._select()
                .with_only_columns(QuestionUnit.unit_id)
                .where(QuestionUnit.question_id == question_id)
            )
        )
        return self.session.scalars(query).all()
