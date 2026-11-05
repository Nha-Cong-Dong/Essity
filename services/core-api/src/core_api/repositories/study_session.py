"""Study sessions of a user (T4.12): every query scoped to them (ARCH §6.2)."""

import uuid

from sqlalchemy import func, select

from core_api.db.models import (
    DocSection,
    Document,
    NoteFile,
    SessionRange,
    StudySession,
    Submission,
)
from core_api.repositories.base import UserScopedRepository
from core_api.repositories.subject import SubjectRepository


class StudySessionRepository(UserScopedRepository[StudySession]):
    model = StudySession

    def create_draft(self, subject_id: uuid.UUID, description: str) -> StudySession:
        """A draft holding the learner's own words (layer 1). The subject is held FOR SHARE until
        commit, so it is not deleted under the draft; SubjectNotFoundError if the user cannot see
        it. `extraction` starts as "failed": the safe answer if the process dies before the card."""
        SubjectRepository(self.session, self.user_id).hold_for_share(subject_id)
        draft = self.add(
            StudySession(subject_id=subject_id, description_raw=description, extraction="failed")
        )
        self.session.flush()
        return draft

    def has_outline(self, subject_id: uuid.UUID) -> bool:
        """The subject has an outline: a textbook (not rejected or failed) with at least one
        section. Progress is the textbook's outline, so without it there is nothing to study."""
        return (
            self.session.scalars(
                select(DocSection.id)
                .join(Document, Document.id == DocSection.document_id)
                .where(
                    DocSection.user_id == self.user_id,
                    DocSection.subject_id == subject_id,
                    Document.user_id == self.user_id,
                    Document.role == "textbook",
                    Document.status.not_in(("rejected", "failed")),
                )
                .limit(1)
            ).first()
            is not None
        )

    def open_draft(self, subject_id: uuid.UUID, description: str) -> StudySession | None:
        """The newest draft of the subject that still holds `description` (the empty-draft
        placeholder) and has no submission yet: the one "Ghi buổi học" continues (US-02 AC1)."""
        return self.session.scalars(
            self._select()
            .where(
                StudySession.subject_id == subject_id,
                StudySession.status == "draft",
                StudySession.description_raw == description,
                ~select(Submission.id).where(Submission.session_id == StudySession.id).exists(),
            )
            .order_by(StudySession.created_at.desc(), StudySession.id)
            .limit(1)
        ).first()

    def last_end_pages(self, subject_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """The last FILE page of confirmed sessions, by document, for "học tiếp"."""
        rows = self.session.execute(
            select(SessionRange.document_id, func.max(SessionRange.end_page))
            .join(StudySession, StudySession.id == SessionRange.session_id)
            .where(
                StudySession.user_id == self.user_id,
                SessionRange.user_id == self.user_id,
                StudySession.subject_id == subject_id,
                StudySession.status == "confirmed",
            )
            .group_by(SessionRange.document_id)
        )
        return {document_id: last for document_id, last in rows}

    def lock(self, id: uuid.UUID) -> StudySession | None:
        """This user's session, held FOR UPDATE until commit and read afresh: one confirm at a
        time, so a second one finds it confirmed."""
        return self.session.scalars(
            self._select()
            .where(StudySession.id == id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()

    def ranges_of(self, session_id: uuid.UUID) -> list[SessionRange]:
        return list(
            self.session.scalars(
                select(SessionRange)
                .where(SessionRange.session_id == session_id, SessionRange.user_id == self.user_id)
                .order_by(SessionRange.position)
            )
        )

    def notes_of(self, session_id: uuid.UUID) -> list[NoteFile]:
        return list(
            self.session.scalars(
                select(NoteFile)
                .where(NoteFile.session_id == session_id, NoteFile.user_id == self.user_id)
                .order_by(NoteFile.created_at, NoteFile.sha256)
            )
        )
