"""Study sessions of a user (T4.12): every query scoped to them (ARCH §6.2)."""

import uuid

from sqlalchemy import func, select

from core_api.db.models import SessionRange, StudySession
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
