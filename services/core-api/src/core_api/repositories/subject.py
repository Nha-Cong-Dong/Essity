import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import Select, exists, select

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

    def create_with_exam(self, name: str, exam_date: date) -> tuple[Subject, Exam]:
        """A subject with its one exam (Q17), in the caller's transaction."""
        subject = self.create(name)
        self.session.flush()
        exam = ExamRepository(self.session, self.user_id).create(subject.id, exam_date)
        self.session.flush()
        return subject, exam

    def _with_exam(self) -> Select[tuple[Subject, Exam]]:
        # Inner join: every subject made through the API has its exam (one, by the database).
        return self._select().add_columns(Exam).join(Exam, Exam.subject_id == Subject.id)

    def list_with_exams(self) -> list[tuple[Subject, Exam]]:
        """Soonest exam first; subjects created first come first on the same day."""
        query = self._with_exam().order_by(Exam.exam_date, Subject.created_at, Subject.id)
        return [(subject, exam) for subject, exam in self.session.execute(query)]

    def get_with_exam(self, id: uuid.UUID) -> tuple[Subject, Exam] | None:
        row = self.session.execute(self._with_exam().where(Subject.id == id)).one_or_none()
        return None if row is None else (row[0], row[1])

    def update(
        self, id: uuid.UUID, *, name: str | None = None, exam_date: date | None = None
    ) -> tuple[Subject, Exam] | None:
        """Change what is given. None if the subject is not this user's (or deleted)."""
        found = self.get_with_exam(id)
        if found is None:
            return None
        subject, exam = found
        if name is not None:
            subject.name = name
        if exam_date is not None:
            exam.exam_date = exam_date
        self.session.flush()
        return subject, exam

    def has_any(self) -> bool:
        """Whether the user has a subject web lists: not deleted, with its exam."""
        return bool(self.session.scalar(select(exists(self._with_exam()))))

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
