"""Outline sections of a user (T7.4): every query scoped to them (ARCH §6.2)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from core_api.db.models import DocSection, KnowledgeUnit, QuestionSection, UnitSection
from core_api.domain import outline as rules
from core_api.repositories.base import UserScopedRepository

# unit.status values that count as a card the learner owns (not a draft, not retired).
_LIVE_CARD = ("canonical",)


def excluded_effective_ids(
    session: Session, user_id: uuid.UUID, subject_id: uuid.UUID
) -> set[uuid.UUID]:
    """Sections of the subject that are excluded or sit under an excluded ancestor (T7.2c)."""
    rows = session.execute(
        select(DocSection.id, DocSection.parent_id, DocSection.excluded).where(
            DocSection.user_id == user_id, DocSection.subject_id == subject_id
        )
    ).all()
    parent = {r.id: r.parent_id for r in rows}
    flagged = {r.id for r in rows if r.excluded}

    def gone(section_id: uuid.UUID) -> bool:
        seen: set[uuid.UUID] = set()
        node: uuid.UUID | None = section_id
        while node is not None and node not in seen:
            if node in flagged:
                return True
            seen.add(node)
            node = parent.get(node)
        return False

    return {i for i in parent if gone(i)}


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

    def referenced_ids(self, document_id: uuid.UUID) -> set[uuid.UUID]:
        """Sections of the document that a card or a question hangs on (a link or `section_id`)."""
        ids = select(DocSection.id).where(
            DocSection.user_id == self.user_id, DocSection.document_id == document_id
        )
        found: set[uuid.UUID] = set(
            self.session.scalars(
                select(UnitSection.section_id).where(
                    UnitSection.user_id == self.user_id, UnitSection.section_id.in_(ids)
                )
            )
        )
        found.update(
            self.session.scalars(
                select(QuestionSection.section_id).where(
                    QuestionSection.user_id == self.user_id, QuestionSection.section_id.in_(ids)
                )
            )
        )
        found.update(
            sid
            for sid in self.session.scalars(
                select(KnowledgeUnit.section_id).where(
                    KnowledgeUnit.user_id == self.user_id, KnowledgeUnit.section_id.in_(ids)
                )
            )
            if sid is not None
        )
        return found

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

    def merge(
        self, document_id: uuid.UUID, subject_id: uuid.UUID, nodes: Sequence[NewSection]
    ) -> list[DocSection]:
        """Lay a new reading over the sections the learner has worked on, keeping their ids (so
        cards, questions and the ledger stay linked). A new section matching an old one
        (`domain.outline.match_titles`) takes its title, unit and, unless the learner set the
        range, its pages, weight and place; progress and exclusion stay. A new section with no
        match is added. An old one the reading no longer has is deleted only when nothing hangs
        on it (no coverage, no edit, no link); else it is kept and excluded."""
        old = self.of_document(document_id)
        position = {o.id: i for i, o in enumerate(old)}
        matched = rules.match_titles(
            [o.title for o in old],
            [n.title for n in nodes],
            [None if o.parent_id is None else position.get(o.parent_id) for o in old],
            [n.parent for n in nodes],
        )
        referenced = self.referenced_ids(document_id)
        made: list[DocSection] = []
        siblings: dict[int | None, int] = {}
        for index, node in enumerate(nodes):
            position = siblings.get(node.parent, 0)
            siblings[node.parent] = position + 1
            parent_id = None if node.parent is None else made[node.parent].id
            if index in matched:
                row = old[matched[index]]
                row.title, row.unit = node.title, node.unit
                row.parent_id, row.ord = parent_id, position
                if row.source != "user":
                    previous = row.weight
                    row.first_page, row.last_page = node.first_page, node.last_page
                    row.weight, row.source, row.excluded = node.weight, node.source, node.excluded
                    full = row.studied_weight >= previous > 0
                    row.studied_weight = row.weight if full else min(row.studied_weight, row.weight)
                made.append(row)
                continue
            row = DocSection(
                subject_id=subject_id,
                document_id=document_id,
                parent_id=parent_id,
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
        self.session.flush()  # parents re-pointed before anything is deleted
        kept = {m.id for m in made}
        gone = [o for o in old if o.id not in kept]
        held = {
            o.id for o in gone if o.studied_weight > 0 or o.source == "user" or o.id in referenced
        }
        parent_of = {o.id: o.parent_id for o in gone}
        for section_id in list(held):  # an old parent of a kept section stays too
            above = parent_of.get(section_id)
            while above is not None and above in parent_of and above not in held:
                held.add(above)
                above = parent_of[above]
        for o in gone:
            if o.id in held:
                o.excluded = True
        drop = [o.id for o in gone if o.id not in held]
        if drop:
            for o in gone:
                if o.id in drop:
                    self.session.expunge(o)
            self.session.execute(
                delete(DocSection).where(
                    DocSection.user_id == self.user_id, DocSection.id.in_(drop)
                )
            )
        self.session.flush()
        return made
