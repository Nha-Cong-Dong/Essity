"""What the suggestions read (T7.10b, US-15): the ledger, each subject's leaves in syllabus order
and the active "prerequisite" edges. Every query is scoped to the user. Writing the ledger stays
in `UnitRepository.ledger_add` (the Save transaction, T7.8)."""

import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from core_api.db.models import DocSection, Document, StudyLedger, UnitEdge, UnitSection
from core_api.domain.graph import Edge, EdgeKind, EdgeStatus, prerequisite_leaves
from core_api.domain.study_ledger import LedgerEntry
from core_api.domain.suggest import UNIT_LABELS, Leaf
from core_api.repositories.base import UserScopedRepository


class StudyLedgerRepository(UserScopedRepository[StudyLedger]):
    model = StudyLedger

    def entries(self) -> list[LedgerEntry]:
        return [
            LedgerEntry(r.subject_id, r.learning_day, r.section_id, r.units_saved)
            for r in self.session.scalars(self._select())
        ]

    def leaves(self) -> dict[uuid.UUID, list[Leaf]]:
        """Leaf sections per subject: documents oldest first, each outline depth first by `ord`."""
        rows = self.session.execute(
            select(DocSection, Document.created_at)
            .join(
                Document,
                (Document.id == DocSection.document_id) & (Document.user_id == self.user_id),
            )
            .where(
                DocSection.user_id == self.user_id, Document.status.not_in(("rejected", "failed"))
            )
        ).all()
        by_doc: dict[uuid.UUID, list[DocSection]] = defaultdict(list)
        created: dict[uuid.UUID, datetime] = {}
        for section, at in rows:
            by_doc[section.document_id].append(section)
            created[section.document_id] = at
        prerequisites = self._prerequisites({s.id for s, _ in rows})
        out: dict[uuid.UUID, list[Leaf]] = defaultdict(list)
        for doc_id in sorted(by_doc, key=lambda d: (created[d], str(d))):
            sections = by_doc[doc_id]
            children: dict[uuid.UUID | None, list[DocSection]] = defaultdict(list)
            for s in sections:
                children[s.parent_id].append(s)
            for kids in children.values():
                kids.sort(key=lambda s: (s.ord, str(s.id)))
            stack = list(reversed(children[None]))
            while stack:
                s = stack.pop()
                if s.id in children:
                    stack.extend(reversed(children[s.id]))
                else:
                    out[s.subject_id].append(
                        Leaf(
                            id=s.id,
                            title=s.title,
                            weight=s.weight,
                            unit=UNIT_LABELS.get(s.unit, s.unit),
                            excluded=s.excluded,
                            covered_weight=s.studied_weight,
                            prerequisites=prerequisites.get(s.id, ()),
                        )
                    )
        return out

    def _prerequisites(self, section_ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[uuid.UUID, ...]]:
        """Leaf -> leaves it needs first, from active edges between cards (T9.9a rule)."""
        edges = [
            Edge(EdgeKind.PREREQUISITE, e.src_unit_id, e.dst_unit_id, EdgeStatus.ACTIVE)
            for e in self.session.scalars(
                select(UnitEdge).where(
                    UnitEdge.user_id == self.user_id,
                    UnitEdge.kind == "prerequisite",
                    UnitEdge.status == "active",
                )
            )
        ]
        if not edges:
            return {}
        card_leaf: dict[uuid.UUID, uuid.UUID] = {}
        for unit_id, section_id in self.session.execute(
            select(UnitSection.unit_id, UnitSection.section_id)
            .where(UnitSection.user_id == self.user_id)
            .order_by(UnitSection.section_id)
        ):
            if section_id in section_ids:
                card_leaf.setdefault(unit_id, section_id)
        return prerequisite_leaves(edges, card_leaf)
