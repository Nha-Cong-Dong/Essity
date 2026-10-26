import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
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
    again would keep the old one in silence (review 8a92b17). Changing a seeded question is
    `QuestionRepository.replace` (T2.2, the seed script's --replace-changed)."""


class QuestionRetiredError(ValueError):
    """The subject had this question and retired it: adding it again would bring it back in
    silence (plan D13)."""


class SubjectMismatchError(ValueError):
    """A question and a unit of different subjects (plan D9)."""


class QuestionRepository(UserScopedRepository[Question]):
    model = Question

    def retire(self, id: uuid.UUID) -> bool:
        """ "Bỏ câu này" (US-09 AC4): the question is never chosen again; what was asked of it
        stays in the history. False when it is not this user's. Retiring twice is the same."""
        question = self.get(id)
        if question is None:
            return False
        question.status = "retired"
        self.session.flush()
        return True

    def find_by_prompt(self, subject_id: uuid.UUID, prompt: str) -> Question | None:
        """The subject's question with this prompt however typed (same content hash): the active
        one, else the newest retired one, else None."""
        query = (
            self._select()
            .where(Question.subject_id == subject_id, Question.content_hash == content_hash(prompt))
            .order_by((Question.status == "active").desc(), Question.created_at.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(query).first()

    def _insert_active(
        self,
        subject_id: uuid.UUID,
        *,
        level: int,
        prompt: str,
        reference_answer: str,
        run_id: uuid.UUID,
        rubric: Any | None,
    ) -> None:
        """Insert unless an active question with this hash is already there (the partial unique
        index, T2.2): two seeds at once add one."""
        self.session.execute(
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
                content_hash=content_hash(prompt),
                run_id=run_id,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "subject_id", "content_hash"],
                index_where=text("status = 'active'"),
            )
        )

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
        returns the existing row instead of a second one, never nothing (plan D12). A question
        that was retired is not brought back (D13)."""
        if SubjectRepository(self.session, self.user_id).get(subject_id) is None:
            raise SubjectNotFoundError(subject_id)
        self.session.flush()
        existing = self.find_by_prompt(subject_id, prompt)
        if existing is not None and existing.status != "active":
            raise QuestionRetiredError(existing.id)
        if existing is None:
            self._insert_active(
                subject_id,
                level=level,
                prompt=prompt,
                reference_answer=reference_answer,
                run_id=run_id,
                rubric=rubric,
            )
            existing = self.find_by_prompt(subject_id, prompt)
        assert existing is not None
        if existing.status != "active":  # retired between the read and the insert
            raise QuestionRetiredError(existing.id)
        if (existing.level, existing.reference_answer, existing.rubric) != (
            level,
            reference_answer,
            rubric,
        ):
            raise QuestionConflictError(existing.id)
        return existing

    def replace(
        self,
        old_id: uuid.UUID,
        *,
        level: int,
        reference_answer: str,
        run_id: uuid.UUID,
        rubric: Any | None = None,
    ) -> Question:
        """Change a seeded question without editing it (T2.2): retire the old one, whose history
        stays true to what it asked, and add a new active one with the same prompt. The caller
        links the units. QuestionNotFoundError when it is not this user's."""
        old = self.get(old_id)
        if old is None:
            raise QuestionNotFoundError(old_id)
        self.retire(old_id)
        self._insert_active(
            old.subject_id,
            level=level,
            prompt=old.prompt,
            reference_answer=reference_answer,
            run_id=run_id,
            rubric=rubric,
        )
        new = self.find_by_prompt(old.subject_id, old.prompt)
        assert new is not None and new.status == "active"
        return new


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

    def link_once(self, question_id: uuid.UUID, unit_id: uuid.UUID) -> bool:
        """`link`, unless the pair is already there. Returns whether it added one."""
        found = self.session.scalars(
            self._select()
            .where(QuestionUnit.question_id == question_id, QuestionUnit.unit_id == unit_id)
            .limit(1)
        ).first()
        if found is not None:
            return False
        self.link(question_id, unit_id)
        return True

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
