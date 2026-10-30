"""Knowledge-graph edges (T9.9a, US-19). Pure: no database, no I/O, no LLM.

- AC1: edge kinds are enums; there is no generic "related" kind.
- AC2: a proposed card-to-card edge needs evidence quotes that really occur in the anchors; no
  valid evidence, a self-loop or a cross-subject pair is rejected.
- PLAN T9.9: re-sent `unit.saved` yields no duplicate edge; a merged/split/deleted card turns its
  edges inactive; proposal calls grow linearly with the number of cards.
- US-15 AC2: active "prerequisite" edges are exposed as the leaf map `suggest` consumes.

Small choices the docs leave open (recorded in the T9.9a decisions): a "prerequisite" edge reads
"source needs target first"; every quote must be valid and at least one is required; quotes are
compared after NFC and whitespace normalisation, case-sensitive; "contrast" is symmetric.
"""

import unicodedata
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

PROPOSAL_BATCH_SIZE = 10


class EdgeKind(StrEnum):
    CARD_SECTION = "card_section"
    QUESTION_CARD = "question_card"
    PREREQUISITE = "prerequisite"
    PART_OF = "part_of"
    EXAMPLE_OF = "example_of"
    CONTRAST = "contrast"
    APPLIES_TO = "applies_to"


CARD_CARD_KINDS = frozenset(
    {
        EdgeKind.PREREQUISITE,
        EdgeKind.PART_OF,
        EdgeKind.EXAMPLE_OF,
        EdgeKind.CONTRAST,
        EdgeKind.APPLIES_TO,
    }
)
_SYMMETRIC_KINDS = frozenset({EdgeKind.CONTRAST})


class EdgeStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CardChange(StrEnum):
    MERGED = "merged"
    SPLIT = "split"
    DELETED = "deleted"


class Rejection(StrEnum):
    WRONG_KIND = "wrong_kind"
    SELF_LOOP = "self_loop"
    UNKNOWN_CARD = "unknown_card"
    CROSS_SUBJECT = "cross_subject"
    NO_EVIDENCE = "no_evidence"
    EVIDENCE_NOT_FOUND = "evidence_not_found"


@dataclass(frozen=True)
class Anchor:
    card_id: uuid.UUID
    subject_id: uuid.UUID
    text: str


@dataclass(frozen=True)
class Evidence:
    card_id: uuid.UUID
    quote: str


@dataclass(frozen=True)
class EdgeProposal:
    kind: EdgeKind
    source_id: uuid.UUID
    target_id: uuid.UUID
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: Rejection | None = None


@dataclass(frozen=True)
class Edge:
    kind: EdgeKind
    source_id: uuid.UUID
    target_id: uuid.UUID
    status: EdgeStatus = EdgeStatus.ACTIVE
    evidence: tuple[Evidence, ...] = field(default=())


EdgeKey = tuple[EdgeKind, uuid.UUID, uuid.UUID]


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _reject(reason: Rejection) -> Verdict:
    return Verdict(False, reason)


def validate_edge(proposal: EdgeProposal, anchors: Mapping[uuid.UUID, Anchor]) -> Verdict:
    """AC2: only card-to-card kinds are proposed by the system."""
    if proposal.kind not in CARD_CARD_KINDS:
        return _reject(Rejection.WRONG_KIND)
    if proposal.source_id == proposal.target_id:
        return _reject(Rejection.SELF_LOOP)
    source = anchors.get(proposal.source_id)
    target = anchors.get(proposal.target_id)
    if source is None or target is None:
        return _reject(Rejection.UNKNOWN_CARD)
    if source.subject_id != target.subject_id:
        return _reject(Rejection.CROSS_SUBJECT)
    if not proposal.evidence:
        return _reject(Rejection.NO_EVIDENCE)
    for item in proposal.evidence:
        anchor = anchors.get(item.card_id)
        quote = normalize(item.quote)
        if item.card_id not in (source.card_id, target.card_id) or anchor is None:
            return _reject(Rejection.EVIDENCE_NOT_FOUND)
        if not quote or quote not in normalize(anchor.text):
            return _reject(Rejection.EVIDENCE_NOT_FOUND)
    return Verdict(True)


def edge_key(kind: EdgeKind, source_id: uuid.UUID, target_id: uuid.UUID) -> EdgeKey:
    if kind in _SYMMETRIC_KINDS and str(target_id) < str(source_id):
        source_id, target_id = target_id, source_id
    return (kind, source_id, target_id)


def merge_proposals(
    existing: Iterable[EdgeKey], proposals: Iterable[EdgeProposal]
) -> list[EdgeProposal]:
    """Proposals not yet stored and not repeated inside the list, in input order."""
    seen = set(existing)
    fresh: list[EdgeProposal] = []
    for proposal in proposals:
        key = edge_key(proposal.kind, proposal.source_id, proposal.target_id)
        if key not in seen:
            seen.add(key)
            fresh.append(proposal)
    return fresh


def deactivate_edges(
    edges: Iterable[Edge], change: CardChange, card_ids: Iterable[uuid.UUID]
) -> list[Edge]:
    """A merged, split or deleted card voids every edge touching it (the card is replaced)."""
    del change  # all three changes have the same effect on edges
    touched = set(card_ids)
    return [
        replace(e, status=EdgeStatus.INACTIVE)
        if e.status is EdgeStatus.ACTIVE and (e.source_id in touched or e.target_id in touched)
        else e
        for e in edges
    ]


def proposal_batches(
    card_ids: Sequence[uuid.UUID], batch_size: int = PROPOSAL_BATCH_SIZE
) -> list[list[uuid.UUID]]:
    """One LLM call per batch: calls = ceil(cards / batch_size), linear in cards."""
    return [list(card_ids[i : i + batch_size]) for i in range(0, len(card_ids), batch_size)]


def prerequisite_leaves(
    edges: Iterable[Edge], card_leaf: Mapping[uuid.UUID, uuid.UUID]
) -> dict[uuid.UUID, tuple[uuid.UUID, ...]]:
    """Leaf id -> prerequisite leaf ids, in the shape of `suggest.Leaf.prerequisites`.

    An active "prerequisite" edge (source needs target) between cards of two different leaves.
    """
    result: dict[uuid.UUID, list[uuid.UUID]] = {}
    for e in edges:
        if e.kind is not EdgeKind.PREREQUISITE or e.status is not EdgeStatus.ACTIVE:
            continue
        needs, needed = card_leaf.get(e.source_id), card_leaf.get(e.target_id)
        if needs is None or needed is None or needs == needed:
            continue
        if needed not in result.setdefault(needs, []):
            result[needs].append(needed)
    return {leaf: tuple(ids) for leaf, ids in result.items()}
