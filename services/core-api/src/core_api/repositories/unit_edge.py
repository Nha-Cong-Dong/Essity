"""Card-to-card edges (T9.9, US-19). Every query is scoped to the user (ARCH 6.2). The text the
edges are checked against (anchored quotes) is read here too, so the service holds no SQL."""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core_api.db.models import (
    Anchor,
    DocSection,
    Document,
    KnowledgeUnit,
    Question,
    QuestionUnit,
    UnitEdge,
    UnitSection,
)
from core_api.domain.graph import EdgeKey, EdgeKind, edge_key
from core_api.repositories.base import UserScopedRepository

MAX_QUOTES = 5
MAX_QUOTE_CHARS = 1000


class UnitEdgeRepository(UserScopedRepository[UnitEdge]):
    model = UnitEdge

    def candidate_cards(self, unit: KnowledgeUnit, limit: int) -> Sequence[KnowledgeUnit]:
        """Other saved cards of the same subject, the ones that share an outline section with
        `unit` first, then the newest. `limit` keeps one Save to one model call."""
        mine = select(UnitSection.section_id).where(
            UnitSection.user_id == self.user_id, UnitSection.unit_id == unit.id
        )
        shares = exists().where(
            UnitSection.user_id == self.user_id,
            UnitSection.unit_id == KnowledgeUnit.id,
            UnitSection.section_id.in_(mine),
        )
        return self.session.scalars(
            select(KnowledgeUnit)
            .where(
                KnowledgeUnit.user_id == self.user_id,
                KnowledgeUnit.subject_id == unit.subject_id,
                KnowledgeUnit.id != unit.id,
                KnowledgeUnit.status == "canonical",
                KnowledgeUnit.retired_at.is_(None),
            )
            .order_by(shares.desc(), KnowledgeUnit.created_at.desc(), KnowledgeUnit.id)
            .limit(limit)
        ).all()

    def quotes(self, unit_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """The first anchored quotes of each card, cut to the sizes ai-service accepts."""
        out: dict[uuid.UUID, list[str]] = {}
        rows = self.session.execute(
            select(Anchor.unit_id, Anchor.quote_text)
            .where(Anchor.user_id == self.user_id, Anchor.unit_id.in_(list(unit_ids)))
            .order_by(Anchor.created_at, Anchor.id)
        )
        for unit_id, quote in rows:
            quotes = out.setdefault(unit_id, [])
            if len(quotes) < MAX_QUOTES:
                quotes.append(quote[:MAX_QUOTE_CHARS])
        return out

    def keys_touching(self, unit_id: uuid.UUID) -> set[EdgeKey]:
        """Every stored edge of the card, whatever its status: an edge the learner removed
        (`rejected`) or that went `inactive` is not proposed again."""
        rows = self.session.execute(
            select(UnitEdge.kind, UnitEdge.src_unit_id, UnitEdge.dst_unit_id).where(
                UnitEdge.user_id == self.user_id,
                (UnitEdge.src_unit_id == unit_id) | (UnitEdge.dst_unit_id == unit_id),
            )
        )
        return {edge_key(EdgeKind(k), s, d) for k, s, d in rows}

    def insert_ai_edge(
        self,
        *,
        subject_id: uuid.UUID,
        kind: EdgeKind,
        src: uuid.UUID,
        dst: uuid.UUID,
        evidence: list[dict[str, str]],
        run_id: uuid.UUID | None,
    ) -> bool:
        """Active at once (the learner removes a wrong one with one tap). A pair already stored
        is left alone: two jobs for one card cannot double it. True when a row was made."""
        if kind is EdgeKind.CONTRAST and str(dst) < str(src):
            src, dst = dst, src  # one way only: the database refuses src > dst
        done = self.session.execute(
            pg_insert(UnitEdge)
            .values(
                id=uuid.uuid4(),
                user_id=self.user_id,
                subject_id=subject_id,
                src_unit_id=src,
                dst_unit_id=dst,
                kind=kind.value,
                origin="ai",
                status="active",
                evidence=evidence,
                run_id=run_id,
            )
            .on_conflict_do_nothing(index_elements=["src_unit_id", "dst_unit_id", "kind"])
            .returning(UnitEdge.id)
        )
        return done.first() is not None

    def find(self, kind: EdgeKind, src: uuid.UUID, dst: uuid.UUID) -> UnitEdge | None:
        return self.session.scalars(
            self._select().where(
                UnitEdge.src_unit_id == src,
                UnitEdge.dst_unit_id == dst,
                UnitEdge.kind == kind.value,
            )
        ).one_or_none()

    # --- the graph screen (T9.10, US-19 AC3-AC4): reads only, all of this user's ---

    def graph_sections(self, subject_id: uuid.UUID) -> list[DocSection]:
        """Every outline section of the subject, in outline order."""
        return list(
            self.session.scalars(
                select(DocSection)
                .where(DocSection.user_id == self.user_id, DocSection.subject_id == subject_id)
                .order_by(DocSection.document_id, DocSection.ord, DocSection.id)
            )
        )

    def graph_units(self, subject_id: uuid.UUID) -> list[KnowledgeUnit]:
        """The canonical, not retired cards: the only nodes the graph draws."""
        return list(
            self.session.scalars(
                select(KnowledgeUnit)
                .where(
                    KnowledgeUnit.user_id == self.user_id,
                    KnowledgeUnit.subject_id == subject_id,
                    KnowledgeUnit.status == "canonical",
                    KnowledgeUnit.retired_at.is_(None),
                )
                .order_by(KnowledgeUnit.created_at, KnowledgeUnit.id)
            )
        )

    def graph_unit_sections(
        self, unit_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """Section ids per card in the order written (the first is the card's own place)."""
        found: dict[uuid.UUID, list[uuid.UUID]] = {}
        rows = self.session.execute(
            select(UnitSection.unit_id, UnitSection.section_id)
            .where(UnitSection.user_id == self.user_id, UnitSection.unit_id.in_(list(unit_ids)))
            .order_by(UnitSection.created_at, UnitSection.id)
        )
        for unit_id, section_id in rows:
            found.setdefault(unit_id, []).append(section_id)
        return found

    def graph_edges(self, unit_ids: Sequence[uuid.UUID]) -> list[UnitEdge]:
        """Active edges with BOTH ends among `unit_ids` (so never one that touches a draft, a
        retired or a hidden card)."""
        ids = list(unit_ids)
        return list(
            self.session.scalars(
                self._select()
                .where(
                    UnitEdge.status == "active",
                    UnitEdge.src_unit_id.in_(ids),
                    UnitEdge.dst_unit_id.in_(ids),
                )
                .order_by(UnitEdge.created_at, UnitEdge.id)
            )
        )

    def graph_anchors(
        self, unit_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, str | None, int | None, str]]]:
        """(anchor id, document name, page, quote) per card, the first `MAX_QUOTES` of each."""
        out: dict[uuid.UUID, list[tuple[uuid.UUID, str | None, int | None, str]]] = {}
        rows = self.session.execute(
            select(
                Anchor.id, Anchor.unit_id, Document.short_name, Anchor.page_no, Anchor.quote_text
            )
            .outerjoin(
                Document, (Document.id == Anchor.document_id) & (Document.user_id == self.user_id)
            )
            .where(Anchor.user_id == self.user_id, Anchor.unit_id.in_(list(unit_ids)))
            .order_by(Anchor.created_at, Anchor.id)
        )
        for anchor_id, unit_id, name, page, quote in rows:
            held = out.setdefault(unit_id, [])
            if len(held) < MAX_QUOTES:
                held.append((anchor_id, name, page, quote[:MAX_QUOTE_CHARS]))
        return out

    def graph_questions(self, unit_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """The questions that need each card (up to `MAX_QUOTES`), cut for display."""
        out: dict[uuid.UUID, list[str]] = {}
        rows = self.session.execute(
            select(QuestionUnit.unit_id, Question.prompt)
            .join(
                Question,
                (Question.id == QuestionUnit.question_id) & (Question.user_id == self.user_id),
            )
            .where(QuestionUnit.user_id == self.user_id, QuestionUnit.unit_id.in_(list(unit_ids)))
            .order_by(Question.created_at, Question.id)
        )
        for unit_id, prompt in rows:
            held = out.setdefault(unit_id, [])
            if len(held) < MAX_QUOTES:
                held.append(prompt[:300])
        return out
