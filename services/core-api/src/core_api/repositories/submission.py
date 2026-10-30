"""Submissions and the outline they are resolved against (T7.6): scoped to the user."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from core_api.db.models import DocSection, KnowledgeUnit, Submission, UnitSection
from core_api.repositories.base import UserScopedRepository


class SubmissionRepository(UserScopedRepository[Submission]):
    model = Submission

    def of_session(self, session_id: uuid.UUID) -> Submission | None:
        """The submission of a session, the oldest if there were ever more."""
        return self.session.scalars(
            self._select()
            .where(Submission.session_id == session_id)
            .order_by(Submission.created_at, Submission.id)
            .limit(1)
        ).one_or_none()

    def sections_of(self, document_ids: Sequence[uuid.UUID]) -> list[DocSection]:
        """The outlines of these documents, in tree order."""
        if not document_ids:
            return []
        return list(
            self.session.scalars(
                select(DocSection)
                .where(DocSection.user_id == self.user_id, DocSection.document_id.in_(document_ids))
                .order_by(DocSection.document_id, DocSection.ord, DocSection.id)
            )
        )

    def units_of_sections(
        self, subject_id: uuid.UUID, section_ids: Sequence[uuid.UUID], limit: int
    ) -> list[KnowledgeUnit]:
        """Active units that cover any of these sections, newest first."""
        if not section_ids:
            return []
        return list(
            self.session.scalars(
                select(KnowledgeUnit)
                .join(UnitSection, UnitSection.unit_id == KnowledgeUnit.id)
                .where(
                    KnowledgeUnit.user_id == self.user_id,
                    UnitSection.user_id == self.user_id,
                    KnowledgeUnit.subject_id == subject_id,
                    KnowledgeUnit.status == "active",
                    UnitSection.section_id.in_(section_ids),
                )
                .distinct()
                .order_by(KnowledgeUnit.created_at.desc(), KnowledgeUnit.id)
                .limit(limit)
            )
        )
