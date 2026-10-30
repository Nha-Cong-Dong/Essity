"""Mix due practice questions into Ôn hôm nay (T8.5a, US-03 AC4, US-06 AC8). Pure.

Choices for what the spec leaves open (decisions in `.work/T8.5a/decisions.md`):

- A card takes `MINUTES_PER_QUESTION` (the `today.py` estimate); a practice question takes its
  type's reference time, never less than a card.
- Items are ranked by forgetting risk alone, kind ignored. `risk` is supplied by the caller
  (higher = more likely forgotten; `today.py` weighs recall by the exam window).
- One cap shared by both kinds: `MAX_QUESTIONS` items or `MAX_MINUTES`, whichever comes first.
  An item that does not fit the minutes left is skipped and the next one tried; the cap is never
  exceeded.
- When both kinds are due, each kind holds `KIND_FLOOR` places (its riskiest items) before the
  rest go by risk, in the `NEW_FLOOR` manner; a floor item only gives way to the cap.
- The plan carries no backlog total (US-03 AC4).
- A practice question is in exactly one place: due ones in Ôn only, never-attempted ready ones in
  Luyện tập only (US-06 AC8); a removed or not-ready question is in neither.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from core_api.domain.today import MAX_MINUTES, MAX_QUESTIONS, MINUTES_PER_QUESTION

KIND_FLOOR = 3
CARD_SECONDS = MINUTES_PER_QUESTION * 60

Kind = Literal["card", "practice"]
_KIND_ORDER: dict[Kind, int] = {"card": 0, "practice": 1}


@dataclass(frozen=True)
class MixItem:
    item_id: uuid.UUID
    kind: Kind
    risk: float  # higher = more likely forgotten
    seconds: float


@dataclass(frozen=True)
class MixPlan:
    items: list[MixItem]
    minutes: int  # estimated, rounded up


@dataclass(frozen=True)
class PracticeQuestion:
    """A practice question as the schedule sees it: `due` is meaningful only with `scheduled`."""

    question_id: uuid.UUID
    ready: bool
    scheduled: bool = False  # has a practice_state (attempted at least once)
    due: bool = False
    removed: bool = False


def card_seconds() -> float:
    return CARD_SECONDS


def practice_seconds(ref_time_s: float) -> float:
    """A practice question takes at least as long as a card (US-03 AC4)."""
    return max(ref_time_s, CARD_SECONDS)


def split_practice(
    questions: Iterable[PracticeQuestion],
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """(due for Ôn hôm nay, never attempted for Luyện tập); the two never share a question."""
    due: list[uuid.UUID] = []
    fresh: list[uuid.UUID] = []
    for q in questions:
        if q.removed or not q.ready:
            continue
        if q.scheduled:
            if q.due:
                due.append(q.question_id)
        else:
            fresh.append(q.question_id)
    return due, fresh


def mix(
    items: Iterable[MixItem],
    *,
    max_minutes: float = MAX_MINUTES,
    max_items: int = MAX_QUESTIONS,
    floor: int = KIND_FLOOR,
) -> MixPlan:
    ranked = sorted(
        {i.item_id: i for i in items}.values(),  # a duplicate id counts once
        key=lambda i: (-i.risk, _KIND_ORDER[i.kind], i.item_id),
    )
    position = {i.item_id: n for n, i in enumerate(ranked)}
    budget = max_minutes * 60
    reserved: set[uuid.UUID] = set()
    if len({i.kind for i in ranked}) > 1:
        for kind in _KIND_ORDER:
            reserved |= {i.item_id for i in [i for i in ranked if i.kind == kind][:floor]}
    order = [i for i in ranked if i.item_id in reserved]
    order += [i for i in ranked if i.item_id not in reserved]
    chosen: list[MixItem] = []
    used = 0.0
    for item in order:
        if len(chosen) < max_items and used + item.seconds <= budget:
            chosen.append(item)
            used += item.seconds
    chosen.sort(key=lambda i: position[i.item_id])
    return MixPlan(chosen, minutes=-int(-used // 60))
