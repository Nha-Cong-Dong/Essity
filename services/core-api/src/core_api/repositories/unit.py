import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.dialects.postgresql import insert

from core_api.db.models import (
    Anchor,
    KnowledgeUnit,
    StudyLedger,
    StudySession,
    UnitLineage,
    UnitRevision,
    UnitSection,
)
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


class UnitLineageRepository(UserScopedRepository[UnitLineage]):
    model = UnitLineage

    def create(
        self, old_unit_id: uuid.UUID, new_unit_id: uuid.UUID, run_id: uuid.UUID
    ) -> UnitLineage:
        """Record that `old_unit_id` went to `new_unit_id`. Both must be this user's
        (UnitNotFoundError otherwise); the database refuses another account's unit all the same."""
        units = KnowledgeUnitRepository(self.session, self.user_id)
        for unit_id in (old_unit_id, new_unit_id):
            if units.get(unit_id) is None:
                raise UnitNotFoundError(unit_id)
        row = self.add(UnitLineage(old_unit_id=old_unit_id, new_unit_id=new_unit_id, run_id=run_id))
        self.session.flush()
        return row


class DraftRepository(KnowledgeUnitRepository):
    """The draft cards of a study session and their revisions and sections (T7.8, US-02b).

    Every write path locks the session first (`lock_session`), then the cards in id order
    (`lock_drafts`): one order everywhere, so a merge and a Save never wait on each other.
    A draft card has `status = 'draft'` and a session; queries here always say so.
    """

    def lock_session(self, session_id: uuid.UUID) -> StudySession | None:
        """This user's session held FOR NO KEY UPDATE until commit: it excludes other review
        writes but not the KEY SHARE that a new card's foreign key takes."""
        return self.session.scalars(
            select(StudySession)
            .where(StudySession.user_id == self.user_id, StudySession.id == session_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        ).one_or_none()

    def lock_drafts(
        self, session_id: uuid.UUID, ids: Sequence[uuid.UUID] | None = None
    ) -> list[KnowledgeUnit]:
        """The session's cards (all of them, or these ids) in any status, locked in id order and
        read afresh. Call `lock_session` first."""
        query = (
            self._select()
            .where(KnowledgeUnit.session_id == session_id)
            .order_by(KnowledgeUnit.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if ids is not None:
            query = query.where(KnowledgeUnit.id.in_(ids))
        return list(self.session.scalars(query))

    def insert_draft(
        self,
        *,
        subject_id: uuid.UUID,
        session_id: uuid.UUID,
        draft_key: str | None,
        title: str,
        summary: str,
        kind: str,
        section_id: uuid.UUID | None,
        run_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """A draft card, or None when this (session, draft_key) is already there (a retried or
        re-sent result, a card the learner retired): ON CONFLICT DO NOTHING on the partial index."""
        values = {
            "id": uuid.uuid4(),
            "user_id": self.user_id,
            "subject_id": subject_id,
            "session_id": session_id,
            "draft_key": draft_key,
            "title": title,
            "summary": summary,
            "kind": kind,
            "status": "draft",
            "section_id": section_id,
            "run_id": run_id,
        }
        statement = insert(KnowledgeUnit).values(**values)
        if draft_key is not None:
            statement = statement.on_conflict_do_nothing(
                index_elements=["session_id", "draft_key"],
                index_where=KnowledgeUnit.draft_key.is_not(None),
            )
        return self.session.execute(statement.returning(KnowledgeUnit.id)).scalar_one_or_none()

    def add_revision(
        self, unit_id: uuid.UUID, rev: int, origin: str, content: dict[str, Any]
    ) -> None:
        self.session.add(
            UnitRevision(
                user_id=self.user_id, unit_id=unit_id, rev=rev, origin=origin, content=content
            )
        )
        self.session.flush()

    def add_sections(
        self, unit_id: uuid.UUID, subject_id: uuid.UUID, section_ids: Sequence[uuid.UUID]
    ) -> None:
        for section_id in section_ids:
            self.session.add(
                UnitSection(
                    user_id=self.user_id,
                    unit_id=unit_id,
                    subject_id=subject_id,
                    section_id=section_id,
                )
            )
        self.session.flush()

    def sections_of(self, unit_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
        """Section ids per unit in the order they were written (the primary first)."""
        rows = self.session.execute(
            select(UnitSection.unit_id, UnitSection.section_id)
            .where(UnitSection.user_id == self.user_id, UnitSection.unit_id.in_(unit_ids))
            .order_by(UnitSection.created_at, UnitSection.id)
        )
        found: dict[uuid.UUID, list[uuid.UUID]] = {}
        for unit_id, section_id in rows:
            found.setdefault(unit_id, []).append(section_id)
        return found

    def revisions_of(self, unit_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[UnitRevision]]:
        rows = self.session.scalars(
            select(UnitRevision)
            .where(UnitRevision.user_id == self.user_id, UnitRevision.unit_id.in_(unit_ids))
            .order_by(UnitRevision.unit_id, UnitRevision.rev)
        )
        found: dict[uuid.UUID, list[UnitRevision]] = {}
        for row in rows:
            found.setdefault(row.unit_id, []).append(row)
        return found

    def anchors_of(self, unit_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[Anchor]]:
        found: dict[uuid.UUID, list[Anchor]] = {}
        for anchor in AnchorRepository(self.session, self.user_id).of_units(unit_ids):
            found.setdefault(anchor.unit_id, []).append(anchor)
        return found

    def drafts_of_session(self, session_id: uuid.UUID) -> list[KnowledgeUnit]:
        """The session's draft cards, oldest first (a retired one is not listed)."""
        return list(
            self.session.scalars(
                self._select()
                .where(KnowledgeUnit.session_id == session_id, KnowledgeUnit.status == "draft")
                .order_by(KnowledgeUnit.created_at, KnowledgeUnit.id)
            )
        )

    def ledger_add(
        self,
        *,
        subject_id: uuid.UUID,
        session_id: uuid.UUID,
        learning_day: Any,
        section_id: uuid.UUID | None,
        count: int,
    ) -> None:
        """Add `count` to the session's ledger row for this day and section (NULL section is one
        value: the unique key is NULLS NOT DISTINCT)."""
        statement = insert(StudyLedger).values(
            id=uuid.uuid4(),
            user_id=self.user_id,
            subject_id=subject_id,
            session_id=session_id,
            learning_day=learning_day,
            section_id=section_id,
            units_saved=count,
        )
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["session_id", "learning_day", "section_id"],
                set_={
                    "units_saved": StudyLedger.units_saved + statement.excluded.units_saved,
                    "updated_at": func.now(),
                },
            )
        )
