import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import Exists, Select, exists, select
from sqlalchemy.orm import QueryableAttribute

from core_api.db.models import Attempt, Exam, Question, Subject
from core_api.repositories.base import UserScopedRepository


class SubjectNotFoundError(LookupError):
    """No such subject for this user: missing, deleted, or someone else's."""


class SubjectHasHistoryError(ValueError):
    """The subject has an attempt, a draft included: it stays (us-01 AC8; T6.3 deletes those)."""


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

    def _history_of(self, subject_id: QueryableAttribute[uuid.UUID] | uuid.UUID) -> Exists:
        """Whether the subject has an attempt, a draft included (plan F2). Both user_id filters
        stand guard though the attempt's foreign key already pairs them (plan F6)."""
        return (
            select(Attempt.id)
            .join(Question, Question.id == Attempt.question_id)
            .where(
                Question.subject_id == subject_id,
                Question.user_id == self.user_id,
                Attempt.user_id == self.user_id,
            )
            .exists()
        )

    def list_with_exams(self) -> list[tuple[Subject, Exam, bool]]:
        """Soonest exam first; subjects created first come first on the same day. The third item
        says whether the subject has review history, so web hides its delete button."""
        query = (
            self._with_exam()
            .add_columns(self._history_of(Subject.id))
            .order_by(Exam.exam_date, Subject.created_at, Subject.id)
        )
        return [(subject, exam, history) for subject, exam, history in self.session.execute(query)]

    def get_with_exam(self, id: uuid.UUID, *, lock: bool = False) -> tuple[Subject, Exam] | None:
        """With `lock`, hold the subject FOR NO KEY UPDATE until commit (plan F10): a delete in
        flight is waited for, and once it commits the subject is not found, so a change never
        lands on a deleted subject. The exam row is not locked."""
        query = self._with_exam().where(Subject.id == id)
        if lock:
            query = query.with_for_update(key_share=True, of=Subject)
        row = self.session.execute(query).one_or_none()
        return None if row is None else (row[0], row[1])

    def update(
        self, id: uuid.UUID, *, name: str | None = None, exam_date: date | None = None
    ) -> tuple[Subject, Exam] | None:
        """Change what is given. None if the subject is not this user's (or deleted). The caller
        locks the subject first (`get_with_exam(id, lock=True)`, plan F10), in the same
        transaction, so a delete in flight is waited for before this reads."""
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

    def soft_delete(self, id: uuid.UUID, now: datetime) -> None:
        """Hide a subject with no review history (us-01 AC8), in the caller's transaction.

        Lock the row FOR UPDATE first: an attempt being written holds the subject FOR SHARE
        (`AttemptRepository.create_draft`), so this waits for it to commit. Only then, in a
        statement of its own, look for history, which therefore sees that attempt (plan F3)."""
        subject = self.session.scalars(
            self._select().where(Subject.id == id).with_for_update()
        ).one_or_none()
        if subject is None:
            raise SubjectNotFoundError(id)
        if self.session.scalar(select(self._history_of(id))):
            raise SubjectHasHistoryError(id)
        subject.deleted_at = now
        self.session.flush()


class ExamRepository(UserScopedRepository[Exam]):
    model = Exam

    def create(self, subject_id: uuid.UUID, exam_date: date) -> Exam:
        if SubjectRepository(self.session, self.user_id).get(subject_id) is None:
            raise SubjectNotFoundError(subject_id)
        return self.add(Exam(subject_id=subject_id, exam_date=exam_date))

    def for_subject(self, subject_id: uuid.UUID) -> Sequence[Exam]:
        query = self._select().where(Exam.subject_id == subject_id).order_by(Exam.exam_date)
        return self.session.scalars(query).all()
