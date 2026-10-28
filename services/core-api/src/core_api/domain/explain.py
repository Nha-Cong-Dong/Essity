"""Why a question is in the session (T5.4, US-07). Pure: no database, no AI.

The reason is data, not a sentence: the web writes the words (DESIGN.md §4, neutral tone).
- "review": the question checks units with a schedule. Its reason comes from the unit the model
  thinks is the least likely to be remembered now (the one that put the question in the session):
  that unit's estimated recall and the whole days since it was last reviewed.
- "new": none of its units has been reviewed; there is no history to cite (us-07 §3).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, MemoryState

_SCHEDULER = FsrsScheduler()


@dataclass(frozen=True)
class Reason:
    kind: Literal["review", "new"]
    retrievability: float | None  # estimated chance of recalling now, 0..1; None for "new"
    days_since_last: int | None  # whole days since the previous review; None for "new"


def explain(states: Sequence[MemoryState], now: datetime) -> Reason:
    """The reason for a question whose units have these schedules (empty: never reviewed)."""
    if not states:
        return Reason(kind="new", retrievability=None, days_since_last=None)
    weakest = min(states, key=lambda s: _SCHEDULER.retrievability(s, now))
    return Reason(
        kind="review",
        retrievability=_SCHEDULER.retrievability(weakest, now),
        days_since_last=max(0, (now - weakest.last_review).days),
    )
