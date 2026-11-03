"""Outline sections of a user (T7.4): every query scoped to them (ARCH §6.2)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select

from core_api.db.models import DocSection, KnowledgeUnit, UnitSection
from core_api.repositories.base import UserScopedRepository

# unit.status values that count as a card the learner owns (not a draft, not retired).
_LIVE_CARD = ("canonical",)


@dataclass(frozen=True)
class NewSection:
    """A section to insert: `parent` is the index in the same list of its parent (before it)."""

    title: str
    parent: int | None
    first_page: int
    last_page: int
    weight: float
    unit: str
    source: str
    # Left out by default (front matter, preface, index...); not an edit of the learner's.
    excluded: bool = False


class DocSectionRepository(UserScopedRepository[DocSection]):
    model = DocSection

    def of_document(self, document_id: uuid.UUID) -> list[DocSection]:
        """Sections of one document in tree order: siblings by `ord`, parents before children."""
        rows = list(
            self.session.scalars(
                self._select()
                .where(DocSection.document_id == document_id)
                .order_by(DocSection.ord, DocSection.id)
            )
        )
        by_parent: dict[uuid.UUID | None, list[DocSection]] = {}
        for row in rows:
            by_parent.setdefault(row.parent_id, []).append(row)
        ordered: list[DocSection] = []

        def walk(parent: uuid.UUID | None) -> None:
            for row in by_parent.get(parent, []):
                ordered.append(row)
                walk(row.id)

        walk(None)
        return ordered

    def by_ids(self, ids: Sequence[uuid.UUID]) -> list[DocSection]:
        """This user's sections among `ids`, in id order (an id of another user is just absent)."""
        return list(
            self.session.scalars(
                self._select()
                .where(DocSection.id.in_(ids))
                .order_by(DocSection.id)
                .execution_options(populate_existing=True)
            )
        )

    def lock_of_documents(self, document_ids: Sequence[uuid.UUID]) -> list[DocSection]:
        """Every section of these documents FOR NO KEY UPDATE in id order, read afresh. That mode
        lets a card insert's KEY SHARE on a sibling pass (the review screen holds its session,
        then inserts under a section). A command writes sections only after this; take the
        documents' own locks first (the outline service's order: document, then sections)."""
        return list(
            self.session.scalars(
                self._select()
                .where(DocSection.document_id.in_(document_ids))
                .order_by(DocSection.id)
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
        )

    def touched(self, document_id: uuid.UUID) -> bool:
        """Whether the learner's work hangs on these sections: an edit of theirs, covered
        pages, or cards linked to them. Such an outline is never replaced by a new reading."""
        owned = self.session.scalar(
            self._select()
            .where(
                DocSection.document_id == document_id,
                (DocSection.source == "user") | (DocSection.studied_weight > 0),
            )
            .limit(1)
            .with_only_columns(func.count())
        )
        return bool(owned) or self.linked_cards(document_id) > 0

    def linked_cards(self, document_id: uuid.UUID) -> int:
        """Live cards linked to a section of the document."""
        return (
            self.session.scalar(
                select(func.count(func.distinct(UnitSection.unit_id)))
                .join(DocSection, DocSection.id == UnitSection.section_id)
                .join(KnowledgeUnit, KnowledgeUnit.id == UnitSection.unit_id)
                .where(
                    UnitSection.user_id == self.user_id,
                    DocSection.document_id == document_id,
                    KnowledgeUnit.status.in_(_LIVE_CARD),
                )
            )
            or 0
        )

    def replace(
        self, document_id: uuid.UUID, subject_id: uuid.UUID, nodes: Sequence[NewSection]
    ) -> list[DocSection]:
        """Swap the document's sections for `nodes` (parents before children)."""
        self.session.execute(
            delete(DocSection).where(
                DocSection.user_id == self.user_id, DocSection.document_id == document_id
            )
        )
        made: list[DocSection] = []
        siblings: dict[int | None, int] = {}
        for index, node in enumerate(nodes):
            position = siblings.get(node.parent, 0)
            siblings[node.parent] = position + 1
            row = DocSection(
                subject_id=subject_id,
                document_id=document_id,
                parent_id=None if node.parent is None else made[node.parent].id,
                ord=position,
                title=node.title,
                first_page=node.first_page,
                last_page=node.last_page,
                weight=node.weight,
                unit=node.unit,
                source=node.source,
                excluded=node.excluded,
            )
            row.id = uuid.uuid4()
            self.add(row)
            made.append(row)
            assert index == len(made) - 1
        self.session.flush()
        return made
