import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import Select

from core_api.db.models import Exam, Subject
from core_api.repositories.base import UserScopedRepository


class SubjectNotFoundError(LookupError):
    """No such subject for this user: missing, deleted, or someone else's."""


class SubjectRepository(UserScopedRepository[Subject]):
    model = Subject

    def _select(self) -> Select[tuple[Subject]]:
        # Soft-deleted subjects stay in the database but are invisible to the app.
        return super()._select().where(Subject.deleted_at.is_(None))

    def create(self, name: str) -> Subject:
        name = name.strip()
        if not name:
            raise ValueError("subject name cannot be blank")
        return self.add(Subject(name=name))

    def soft_delete(self, id: uuid.UUID) -> bool:
        subject = self.get(id)
        if subject is None:
            return False
        subject.deleted_at = datetime.now(UTC)
        return True


class ExamRepository(UserScopedRepository[Exam]):
    model = Exam

    def create(self, subject_id: uuid.UUID, exam_date: date) -> Exam:
        if SubjectRepository(self.session, self.user_id).get(subject_id) is None:
            raise SubjectNotFoundError(subject_id)
        return self.add(Exam(subject_id=subject_id, exam_date=exam_date))

    def for_subject(self, subject_id: uuid.UUID) -> Sequence[Exam]:
        query = self._select().where(Exam.subject_id == subject_id).order_by(Exam.exam_date)
        return self.session.scalars(query).all()
