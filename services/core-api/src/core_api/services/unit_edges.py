"""Edges between cards (T9.9, US-19): the proposal that follows a Save, and the two ways a learner
changes an edge (the command bar of T9.2e calls these; no command op is added here).

`propose_edges_for_unit` is the step the `propose_unit_edges` job runs for one saved card:

- One model call per saved card, at most: the card and up to `PROPOSAL_BATCH_SIZE` candidates (same
  subject, the cards of its outline sections first, then the newest). The calls of N Saves are N,
  however many cards the subject holds; a card with no candidate costs none.
- The model's evidence is a claim. Each quote is checked here against the anchors core holds
  (`domain.graph.validate_edge`): no evidence, a quote not in the anchors, a self-loop or a card
  of another subject (never sent, never stored) means no edge.
- Idempotent: a pair already stored in any status (`rejected` and `inactive` too) is not made
  again, so a re-sent `unit.saved` or a retried job adds nothing.
- The cards linked to outline sections (`unit_section`) and the questions linked to cards
  (`question_unit`) already are rows of their own tables; the graph reads them there.

Logs hold ids and rule names, never card or model text (ADR-0013).
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from core_api.clients.ai_client import NotGraded
from core_api.clients.propose_edges_contract import ProposeEdgesReply
from core_api.db.models import KnowledgeUnit, UnitEdge
from core_api.domain.graph import (
    CARD_CARD_KINDS,
    PROPOSAL_BATCH_SIZE,
    Anchor,
    EdgeKind,
    EdgeProposal,
    Evidence,
    merge_proposals,
    validate_edge,
)
from core_api.handlers.unit_saved import AiUnavailableError
from core_api.repositories.unit_edge import UnitEdgeRepository

_log = logging.getLogger("core_api.services")

Outcome = Literal["created", "none", "no_candidates", "skipped", "pending_ai", "failed"]
_QUOTE_JOIN = "\x00"  # not whitespace: a quote cannot run across two anchors


class ProposeEdgesAi(Protocol):
    def propose_edges(self, payload: dict[str, object]) -> ProposeEdgesReply | NotGraded: ...


class UnknownEdgeError(LookupError):
    pass


def _card_payload(unit: KnowledgeUnit, quotes: list[str]) -> dict[str, object]:
    return {
        "unit_id": str(unit.id),
        "title": unit.title,
        "summary": unit.summary[:1000],
        "quotes": quotes,
    }


def propose_edges_for_unit(
    session: Session, user_id: uuid.UUID, unit_id: uuid.UUID, ai: ProposeEdgesAi
) -> Outcome:
    """The caller commits. Raises `AiUnavailableError` when ai-service cannot be reached (the job
    retries)."""
    repo = UnitEdgeRepository(session, user_id)
    unit = session.get(KnowledgeUnit, unit_id)
    if (
        unit is None
        or unit.user_id != user_id
        or unit.status != "canonical"
        or unit.retired_at is not None
    ):
        return "skipped"
    candidates = list(repo.candidate_cards(unit, PROPOSAL_BATCH_SIZE))
    if not candidates:
        return "no_candidates"
    cards = {unit.id: unit, **{c.id: c for c in candidates}}
    quotes = repo.quotes(cards)
    reply = ai.propose_edges(
        {
            "user_id": str(user_id),
            "subject_id": str(unit.subject_id),
            "source": _card_payload(unit, quotes.get(unit.id, [])),
            "candidates": [_card_payload(c, quotes.get(c.id, [])) for c in candidates],
        }
    )
    extra = {"unit_id": str(unit.id)}
    if isinstance(reply, NotGraded):
        if reply.failure == "unavailable":
            raise AiUnavailableError(reply.reason)
        _log.warning("edges not proposed", extra=extra | {"outcome": reply.reason})
        return "pending_ai" if reply.failure == "quota" else "failed"
    if reply.status != "ok":
        _log.warning("edges not proposed", extra=extra | {"outcome": reply.failure})
        return "pending_ai" if reply.status == "pending_ai" else "failed"
    anchors = {
        c.id: Anchor(c.id, c.subject_id, _QUOTE_JOIN.join(quotes.get(c.id, [])))
        for c in cards.values()
    }
    valid: list[EdgeProposal] = []
    refused = 0
    for item in reply.edges:
        try:
            kind = EdgeKind(item.kind)
        except ValueError:
            refused += 1
            continue
        proposal = EdgeProposal(
            kind,
            item.source_id,
            item.target_id,
            tuple(Evidence(e.unit_id, e.quote) for e in item.evidence),
        )
        touches_saved = unit.id in (item.source_id, item.target_id)
        if kind in CARD_CARD_KINDS and touches_saved and validate_edge(proposal, anchors).ok:
            valid.append(proposal)
        else:
            refused += 1
    made = 0
    for proposal in merge_proposals(repo.keys_touching(unit.id), valid):
        evidence = [{"unit_id": str(e.card_id), "quote": e.quote} for e in proposal.evidence]
        if repo.insert_ai_edge(
            subject_id=unit.subject_id,
            kind=proposal.kind,
            src=proposal.source_id,
            dst=proposal.target_id,
            evidence=evidence,
            run_id=reply.run_id,
        ):
            made += 1
    _log.info("edges proposed", extra=extra | {"edges": made, "refused": refused + reply.dropped})
    return "created" if made else "none"


def reject_edge(session: Session, user_id: uuid.UUID, edge_id: uuid.UUID) -> UnitEdge:
    """The learner removes a wrong edge (AC2): it stays as `rejected`, so it is not proposed
    again. Another user's edge is unknown, not forbidden."""
    edge = UnitEdgeRepository(session, user_id).get(edge_id)
    if edge is None:
        raise UnknownEdgeError(edge_id)
    edge.status = "rejected"
    session.flush()
    return edge


def add_user_edge(
    session: Session, user_id: uuid.UUID, kind: EdgeKind, src: uuid.UUID, dst: uuid.UUID
) -> UnitEdge:
    """A relation the learner states (AC2: any, no evidence needed). Both cards must be the
    user's and of one subject; the database refuses a self-loop."""
    if kind not in CARD_CARD_KINDS:
        raise ValueError("kind")
    if kind is EdgeKind.CONTRAST and str(dst) < str(src):
        src, dst = dst, src
    first, second = session.get(KnowledgeUnit, src), session.get(KnowledgeUnit, dst)
    if first is None or second is None or user_id != first.user_id or user_id != second.user_id:
        raise UnknownEdgeError(src)
    if first.subject_id != second.subject_id:
        raise ValueError("cross_subject")
    repo = UnitEdgeRepository(session, user_id)
    existing = repo.find(kind, src, dst)
    if existing is not None:
        if existing.status != "active":
            existing.status, existing.origin = "active", "user"
            session.flush()
        return existing
    edge = UnitEdge(
        subject_id=first.subject_id,
        src_unit_id=src,
        dst_unit_id=dst,
        kind=kind.value,
        origin="user",
        status="active",
        evidence=[],
    )
    repo.add(edge)
    session.flush()
    return edge


MAX_GRAPH_CARDS = 300  # US-19 AC3; more is cut here and the screen says so, neutrally


class UnknownSectionError(LookupError):
    pass


@dataclass(frozen=True)
class GraphSectionRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    title: str


@dataclass(frozen=True)
class GraphCardRow:
    id: uuid.UUID
    title: str
    summary: str
    section_id: uuid.UUID | None
    anchors: list[tuple[uuid.UUID, str | None, int | None, str]]
    needed_by: list[str]


@dataclass(frozen=True)
class GraphEdgeRow:
    id: uuid.UUID
    kind: str
    src: uuid.UUID
    dst: uuid.UUID
    evidence: list[dict[str, str]]


@dataclass(frozen=True)
class SubjectGraph:
    sections: list[GraphSectionRow]
    cards: list[GraphCardRow]
    edges: list[GraphEdgeRow]
    hidden: int


def subject_graph(
    session: Session,
    user_id: uuid.UUID,
    subject_id: uuid.UUID,
    section_id: uuid.UUID | None = None,
    limit: int = MAX_GRAPH_CARDS,
) -> SubjectGraph:
    """What the graph screen draws (T9.10, US-19 AC3-AC4): canonical cards, the active edges
    between two of them (an edge that touches a draft, retired or hidden card is not returned,
    T9.9 review F1), and the sections that hold a card (any card) or lead to one. `section_id`
    keeps the cards of that section and its subsections. More than `limit` cards: the first ones
    in outline order and the count left out. The caller has already checked the subject is the
    user's."""
    repo = UnitEdgeRepository(session, user_id)
    sections = repo.graph_sections(subject_id)
    by_id = {s.id: s for s in sections}
    scope: set[uuid.UUID] | None = None
    if section_id is not None:
        if section_id not in by_id:
            raise UnknownSectionError(section_id)
        scope = {section_id}
        grew = True
        while grew:
            grew = False
            for s in sections:
                if s.parent_id in scope and s.id not in scope:
                    scope.add(s.id)
                    grew = True
    units = repo.graph_units(subject_id)
    placed = repo.graph_unit_sections([u.id for u in units])
    for u in units:
        # E-15: a card with no link row still sits in its own section.
        if u.id not in placed and u.section_id is not None and u.section_id in by_id:
            placed[u.id] = [u.section_id]
    order = {s.id: i for i, s in enumerate(sections)}
    chosen = [u for u in units if scope is None or scope.intersection(placed.get(u.id, ()))]
    # Outline order, the cards in no section last; then the order the cards were made.
    chosen.sort(key=lambda u: order[placed[u.id][0]] if u.id in placed else len(order))
    shown = chosen[:limit]
    ids = [u.id for u in shown]
    anchors, needed = repo.graph_anchors(ids), repo.graph_questions(ids)
    cards = [
        GraphCardRow(
            id=u.id,
            title=u.title,
            summary=u.summary,
            section_id=placed[u.id][0] if u.id in placed else None,
            anchors=anchors.get(u.id, []),
            needed_by=needed.get(u.id, []),
        )
        for u in shown
    ]
    edges = [
        GraphEdgeRow(
            id=e.id,
            kind=e.kind,
            src=e.src_unit_id,
            dst=e.dst_unit_id,
            evidence=[dict(q) for q in e.evidence],
        )
        for e in repo.graph_edges(ids)
    ]
    # The choice of section lists every section that holds a card (not only the ones shown), so a
    # filter never hides the others.
    keep: set[uuid.UUID] = set()
    for linked in placed.values():
        for held in linked:
            parent: uuid.UUID | None = held
            while parent is not None and parent not in keep:
                keep.add(parent)
                parent = by_id[parent].parent_id
    rows = [GraphSectionRow(s.id, s.parent_id, s.title) for s in sections if s.id in keep]
    return SubjectGraph(rows, cards, edges, len(chosen) - len(shown))
