import uuid
from typing import Any

from core_api.db.models import Anchor, KnowledgeUnit
from core_api.repositories.base import UserScopedRepository
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository


class UnitNotFoundError(LookupError):
    """No such knowledge unit for this user."""


class KnowledgeUnitRepository(UserScopedRepository[KnowledgeUnit]):
    model = KnowledgeUnit

    def create(
        self, subject_id: uuid.UUID, *, title: str, summary: str, kind: str, run_id: uuid.UUID
    ) -> KnowledgeUnit:
        if SubjectRepository(self.session, self.user_id).get(subject_id) is None:
            raise SubjectNotFoundError(subject_id)
        unit = self.add(
            KnowledgeUnit(
                subject_id=subject_id, title=title, summary=summary, kind=kind, run_id=run_id
            )
        )
        self.session.flush()  # gives the unit its id, for the anchors and links that follow
        return unit


class AnchorRepository(UserScopedRepository[Anchor]):
    model = Anchor

    def create(self, unit_id: uuid.UUID, **fields: Any) -> Anchor:
        if KnowledgeUnitRepository(self.session, self.user_id).get(unit_id) is None:
            raise UnitNotFoundError(unit_id)
        anchor = self.add(Anchor(unit_id=unit_id, **fields))
        self.session.flush()
        return anchor
