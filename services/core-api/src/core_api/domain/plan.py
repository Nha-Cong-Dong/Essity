"""Daily study plan by outline unit (hackathon E2, user 04/11). Pure: no database.

A leaf section is the scheduling unit. How many leaves a subject gets on a day follows from the
leaves still open and the days left to the exam, so a subject that is ahead can have days with
nothing suggested ("Học tự do" appears only then). The count shown to the learner as "còn n"
counts chapters (top-level sections), never leaves.
"""

import math
from collections.abc import Sequence
from typing import Protocol

# Without an exam date there is no pace to keep: a small steady amount.
DEFAULT_PER_DAY = 3


class PlanLeaf(Protocol):
    @property
    def open(self) -> bool: ...


def daily_quota(remaining_at_start: int, days_left: int | None, *, can_rest: bool = True) -> int:
    """Units to study today, from the units open at the start of the day.

    Aim to end today with at most ceil(R * (D-1) / D) open: it spreads R units over D days, gives
    0 on days when the subject is ahead (fewer units than days) and everything on the last day.
    `can_rest` False (never studied) keeps at least one unit so a new subject starts at once.
    """
    if remaining_at_start <= 0:
        return 0
    if days_left is None:
        return min(DEFAULT_PER_DAY, remaining_at_start)
    days = max(days_left, 1)
    keep = math.ceil(remaining_at_start * (days - 1) / days)
    quota = remaining_at_start - keep
    if not can_rest:
        quota = max(quota, 1)
    return quota


def todays_units[T: PlanLeaf](
    leaves: Sequence[T], days_left: int | None, learned_today: int, *, can_rest: bool = True
) -> list[T]:
    """The first open leaves, in syllabus order, that still fit today's quota. `learned_today` is
    the number of leaves finished earlier today (they count toward the quota)."""
    open_leaves = [leaf for leaf in leaves if leaf.open]
    quota = daily_quota(len(open_leaves) + learned_today, days_left, can_rest=can_rest)
    return open_leaves[: max(quota - learned_today, 0)]


def remaining_chapters(chapter_keys: Sequence[object]) -> int:
    """Distinct chapters among the keys of the open leaves."""
    return len(set(chapter_keys))
