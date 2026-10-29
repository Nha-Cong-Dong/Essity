"""Study sessions of a user (T4.12): every query scoped to them (ARCH §6.2)."""

import uuid

from sqlalchemy import func, select

from core_api.db.models import NoteFile, SessionRange, StudySession
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
