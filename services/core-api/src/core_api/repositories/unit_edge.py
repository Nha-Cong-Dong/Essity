"""Card-to-card edges (T9.9, US-19). Every query is scoped to the user (ARCH 6.2). The text the
edges are checked against (anchored quotes) is read here too, so the service holds no SQL."""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core_api.db.models import Anchor, KnowledgeUnit, UnitEdge, UnitSection
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
