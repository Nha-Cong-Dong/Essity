"""Reviewing draft cards (T7.8, US-02b AC6-AC9, AC12): the pure rules, no database.

Shared by the review API and the command bar (T9.2). Merging and splitting are deterministic and
never call an LLM (AC6). Only draft cards can be merged, split or edited.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import learning_day

UNDO_WINDOW = timedelta(days=7)
CHANGED_ELSEWHERE = "thẻ đã đổi ở nơi khác"


class UnitChangedElsewhere(Exception):
    """The If-Match version is not the card's current one (409)."""

    message = CHANGED_ELSEWHERE


class NotADraft(Exception):
    """Merge, split or edit asked for a card that is not a draft."""


class UndoExpired(Exception):
    """A discarded card is older than the undo window (410)."""


@dataclass(frozen=True)
class DraftCard:
    id: uuid.UUID
    session_id: uuid.UUID | None
    title: str
    content: str
    kind: str
    status: str
    version: int
    created_at: datetime
    anchor_ids: tuple[uuid.UUID, ...] = ()
    section_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class SplitPart:
    title: str
    content: str
    anchor_ids: tuple[uuid.UUID, ...]


def check_version(current: int, expected: int) -> None:
    if current != expected:
        raise UnitChangedElsewhere


def _require_drafts(cards: list[DraftCard]) -> None:
    if any(c.status != "draft" for c in cards):
        raise NotADraft


def merge(cards: list[DraftCard]) -> tuple[DraftCard, list[DraftCard]]:
    """Keep the oldest card (ties: smaller id), join the contents in that order, union anchors and
    sections. Returns the kept card (same id, content joined) and the cards that become merged."""
    if len(cards) < 2:
        raise ValueError("merge needs at least two cards")
    _require_drafts(cards)
    if len({c.session_id for c in cards}) != 1 or cards[0].session_id is None:
        raise NotADraft
    ordered = sorted(cards, key=lambda c: (c.created_at, str(c.id)))
    keep, rest = ordered[0], ordered[1:]
    kept = DraftCard(
        id=keep.id,
        session_id=keep.session_id,
        title=keep.title,
        content="\n\n".join(c.content for c in ordered),
        kind=keep.kind,
        status="draft",
        version=keep.version + 1,
        created_at=keep.created_at,
        anchor_ids=_union(c.anchor_ids for c in ordered),
        section_ids=_union(c.section_ids for c in ordered),
    )
    return kept, rest


def split(card: DraftCard, parts: list[SplitPart]) -> list[SplitPart]:
    """Check a split request: at least two parts, each with a title and content, anchors only from
    the card (none lost, none shared). Returns the parts unchanged."""
    _require_drafts([card])
    if len(parts) < 2:
        raise ValueError("split needs at least two parts")
    if any(not p.title.strip() or not p.content.strip() for p in parts):
        raise ValueError("every part needs a title and content")
    used = [a for p in parts for a in p.anchor_ids]
    if len(set(used)) != len(used) or not set(used) <= set(card.anchor_ids):
        raise ValueError("anchors must come from the card, each in one part")
    return parts


def can_undo(retired_at: datetime, now: datetime) -> bool:
    return now - retired_at <= UNDO_WINDOW


def require_undo(retired_at: datetime, now: datetime) -> None:
    if not can_undo(retired_at, now):
        raise UndoExpired


def saved_learning_day(now: datetime, tz: ZoneInfo, day_start_hour: int) -> date:
    """The learning day a card is saved on; it enters review on the next one (AC12)."""
    return learning_day(now, tz, day_start_hour)


def in_review(saved_day: date, today: date) -> bool:
    return saved_day < today


def _union(groups: Iterable[tuple[uuid.UUID, ...]]) -> tuple[uuid.UUID, ...]:
    seen: dict[uuid.UUID, None] = {}
    for group in groups:
        for item in group:
            seen.setdefault(item)
    return tuple(seen)
