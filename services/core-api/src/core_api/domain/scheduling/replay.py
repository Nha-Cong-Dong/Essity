"""One review step, and replaying review_log through it (T2.6, ADR-0009).

`schedule_review` is the step every review takes: FSRS, then the exam constraint. The live path
(T2.13) and `replay` both go through it, so memory_state rebuilt from review_log matches the one
reviews wrote, field for field. A replay with a new exam date is also how a moved exam reaches
the schedule (US-01 AC3): the constraint only pulls due dates in, never back out.
"""

from collections.abc import Iterable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core_api.domain.scheduling.exam_constraint import apply_exam_constraint
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, MemoryState
from core_api.domain.scheduling.rating import ReviewRating

_SCHEDULER = FsrsScheduler()


def schedule_review(
    state: MemoryState | None,
    rating: ReviewRating,
    reviewed_at: datetime,
    *,
    exam_day: date,
    tz: ZoneInfo,
    day_start_hour: int,
) -> MemoryState:
    """The state after one review of a unit whose subject's exam is on `exam_day`."""
    reviewed = _SCHEDULER.review(state, rating, reviewed_at)
    return apply_exam_constraint(reviewed, exam_day, tz, day_start_hour)


def replay(
    reviews: Iterable[tuple[ReviewRating, datetime]],
    *,
    exam_day: date,
    tz: ZoneInfo,
    day_start_hour: int,
) -> MemoryState | None:
    """The state of one (unit, facet) from its reviews, oldest first; None if never reviewed."""
    state: MemoryState | None = None
    for rating, reviewed_at in reviews:
        if state is not None and reviewed_at < state.last_review:
            raise ValueError("reviews must be in the order they happened")
        state = schedule_review(
            state, rating, reviewed_at, exam_day=exam_day, tz=tz, day_start_hour=day_start_hour
        )
    return state
