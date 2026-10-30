"""FSRS schedule of one practice question (T8.3a, ADR-0029, US-16, US-06 AC5).

Pure: no database, no I/O. A practice question has its own schedule, independent of any card:
the same FSRS step as cards (`FsrsScheduler`), keyed by question instead of (unit, facet). The
rating comes from the shared mapping in `domain.mastery.rating_for` (Easy needs four conditions).

- First attempt creates the state; a question never attempted has none (`None`).
- `remove` stops the schedule (`due` is None); `readd` resumes it where it left off. An attempt on
  a removed question is still scheduled but the question stays removed until `readd`.
- `replay` folds a log (attempts, removals, re-adds, oldest first) through the same functions as
  the live path, so a rebuilt `practice_state` equals the cached one.
- No exam constraint: it belongs to a subject's cards, and a practice question is not tied to one
  exam date (decision, Coder).
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import day_bounds, learning_day
from core_api.domain.mastery import (
    DEFAULT_CONFIG,
    MasteryConfig,
    PracticeVerdict,
    is_learned,
    rating_for,
)
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, MemoryState

_SCHEDULER = FsrsScheduler()


@dataclass(frozen=True)
class Attempt:
    """One graded attempt. `timing_ok` False means "not measured": never Easy."""

    verdict: PracticeVerdict
    active_seconds: float
    reference_seconds: float
    timing_ok: bool
    at: datetime


@dataclass(frozen=True)
class Removal:
    at: datetime


@dataclass(frozen=True)
class Readd:
    at: datetime


@dataclass(frozen=True)
class PracticeState:
    """Mirrors practice_state: FSRS memory, the last verdict, and when it was removed."""

    memory: MemoryState
    last_verdict: PracticeVerdict
    removed_at: datetime | None = None

    @property
    def due(self) -> datetime | None:
        return None if self.removed_at is not None else self.memory.due


def apply(
    state: PracticeState | None, attempt: Attempt, config: MasteryConfig = DEFAULT_CONFIG
) -> PracticeState:
    previous = state.last_verdict if state is not None else None
    rating = rating_for(
        attempt.verdict,
        attempt.active_seconds,
        attempt.reference_seconds,
        previous,
        attempt.timing_ok,
        config,
    )
    memory = _SCHEDULER.review(state.memory if state else None, rating, attempt.at)
    return PracticeState(
        memory=memory,
        last_verdict=attempt.verdict,
        removed_at=state.removed_at if state is not None else None,
    )


def remove(state: PracticeState | None, at: datetime) -> PracticeState | None:
    """Stop the schedule. A question never attempted has no state, so nothing to stop."""
    if state is None:
        return None
    return replace(state, removed_at=at)


def readd(state: PracticeState) -> PracticeState:
    return replace(state, removed_at=None)


def replay(
    log: Iterable[Attempt | Removal | Readd], config: MasteryConfig = DEFAULT_CONFIG
) -> PracticeState | None:
    """The state from a question's log, oldest first; None if it was never attempted."""
    state: PracticeState | None = None
    for event in log:
        if isinstance(event, Attempt):
            state = apply(state, event, config)
        elif isinstance(event, Removal):
            state = remove(state, event.at)
        elif state is not None:
            state = readd(state)
    return state


def is_known(state: PracticeState, now: datetime, config: MasteryConfig = DEFAULT_CONFIG) -> bool:
    """ "Thuộc": retrievability at `now` >= 90% and the last attempt correct (US-16 AC7 family)."""
    return is_learned(_SCHEDULER.retrievability(state.memory, now), state.last_verdict, config)


def is_due(state: PracticeState, now: datetime, *, tz: ZoneInfo, day_start_hour: int) -> bool:
    """Due by the end of the current learning day, as for cards; removed is never due."""
    if state.due is None:
        return False
    _, end = day_bounds(learning_day(now, tz, day_start_hour), tz, day_start_hour)
    return state.due < end
