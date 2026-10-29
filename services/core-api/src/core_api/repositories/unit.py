import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, update

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

    def for_event(self, subject_id: uuid.UUID, limit: int) -> list[KnowledgeUnit]:
        """The subject's active units that are not skipped, newest first, for the units
        ai-service merges new ones with (session.confirmed.v1)."""
        return list(
            self.session.scalars(
                self._select()
                .where(
                    KnowledgeUnit.subject_id == subject_id,
                    KnowledgeUnit.status == "active",
                    KnowledgeUnit.skipped_at.is_(None),
                )
                .order_by(KnowledgeUnit.created_at.desc(), KnowledgeUnit.id)
                .limit(limit)
            )
        )

    def find_by_title(self, subject_id: uuid.UUID, title: str) -> KnowledgeUnit | None:
        """The subject's active unit with this title, oldest first (the seed script, T2.2)."""
        query = (
            self._select()
            .where(
                KnowledgeUnit.subject_id == subject_id,
                KnowledgeUnit.title == title,
                KnowledgeUnit.status == "active",
            )
            .order_by(KnowledgeUnit.created_at, KnowledgeUnit.id)
        )
        return self.session.scalars(query.limit(1)).first()

    def skip(self, id: uuid.UUID, now: datetime) -> bool:
        """Mark the unit "không cần ôn phần này" (T2.23); False when it is not this user's or is
        already skipped. Schedule and history stay as they are (ADR-0008)."""
        return self._set_skipped(id, KnowledgeUnit.skipped_at.is_(None), now)

    def unskip(self, id: uuid.UUID) -> bool:
        """Undo `skip`; False when it is not this user's or is not skipped."""
        return self._set_skipped(id, KnowledgeUnit.skipped_at.is_not(None), None)

    def _set_skipped(
        self, id: uuid.UUID, state: ColumnElement[bool], value: datetime | None
    ) -> bool:
        done = self.session.execute(
            update(KnowledgeUnit)
            .where(KnowledgeUnit.user_id == self.user_id, KnowledgeUnit.id == id, state)
            .values(skipped_at=value)
            .returning(KnowledgeUnit.id)
        ).first()
        return done is not None

    def lock(self, ids: Sequence[uuid.UUID]) -> None:
        """Hold these units FOR NO KEY UPDATE until commit, in id order (T2.13): two answers on
        one unit graded at once write its schedule one after the other, never over each other.
        NO KEY: review_log's and memory_state's foreign keys take KEY SHARE, which this allows."""
        self.session.execute(
            self._select()
            .with_only_columns(KnowledgeUnit.id)
            .where(KnowledgeUnit.id.in_(ids))
            .order_by(KnowledgeUnit.id)
            .with_for_update(key_share=True)
        ).all()


class AnchorRepository(UserScopedRepository[Anchor]):
    model = Anchor

    def create(self, unit_id: uuid.UUID, **fields: Any) -> Anchor:
        if KnowledgeUnitRepository(self.session, self.user_id).get(unit_id) is None:
            raise UnitNotFoundError(unit_id)
        anchor = self.add(Anchor(unit_id=unit_id, **fields))
        self.session.flush()
        return anchor

    def has_quote(self, unit_id: uuid.UUID, source: str, quote_text: str) -> bool:
        return (
            self.session.scalars(
                self._select()
                .where(
                    Anchor.unit_id == unit_id,
                    Anchor.source == source,
                    Anchor.quote_text == quote_text,
                )
                .limit(1)
            ).first()
            is not None
        )

    def of_units(self, unit_ids: Sequence[uuid.UUID]) -> Sequence[Anchor]:
        """The anchors of these units, oldest first (the sources sent for grading, US-05 AC8)."""
        query = (
            self._select()
            .where(Anchor.unit_id.in_(unit_ids))
            .order_by(Anchor.unit_id, Anchor.created_at, Anchor.id)
        )
        return self.session.scalars(query).all()
