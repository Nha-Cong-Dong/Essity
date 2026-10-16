import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, MemoryState, Phase
from core_api.domain.scheduling.rating import ReviewRating, Verdict, rating_for

START = datetime(2026, 10, 16, 20, 0, tzinfo=UTC)
SRC = Path(__file__).parents[2] / "src"


@pytest.mark.parametrize(
    ("verdict", "rating"),
    [
        (Verdict.CORRECT, ReviewRating.GOOD),
        (Verdict.PARTIAL, ReviewRating.HARD),
        (Verdict.INCORRECT, ReviewRating.AGAIN),
        (Verdict.FORGOT, ReviewRating.AGAIN),
    ],
)
def test_verdict_maps_to_rating(verdict: Verdict, rating: ReviewRating) -> None:
    assert rating_for(verdict) == rating


def test_easy_is_never_produced() -> None:
    assert {rating_for(v) for v in Verdict} == {
        ReviewRating.AGAIN,
        ReviewRating.HARD,
        ReviewRating.GOOD,
    }


def test_wrong_answer_is_due_again_within_one_day() -> None:
    # US-06 AC2, for a new unit and for one that was already well known.
    scheduler = FsrsScheduler()
    new = scheduler.review(None, ReviewRating.AGAIN, START)
    assert new.due - START <= timedelta(days=1)

    known = None
    at = START
    for _ in range(4):
        known = scheduler.review(known, ReviewRating.GOOD, at)
        at = known.due
    lapsed = scheduler.review(known, ReviewRating.AGAIN, at)
    assert lapsed.due - at <= timedelta(days=1)


def test_three_correct_answers_in_a_row_give_growing_intervals() -> None:
    # US-06 AC2
    scheduler = FsrsScheduler()
    state = None
    at = START
    intervals: list[timedelta] = []
    for _ in range(3):
        state = scheduler.review(state, ReviewRating.GOOD, at)
        intervals.append(state.due - at)
        at = state.due
    assert intervals[0] < intervals[1] < intervals[2]


def test_ratings_order_the_next_interval() -> None:
    scheduler = FsrsScheduler()
    base = scheduler.review(None, ReviewRating.GOOD, START)
    at = base.due
    due = {r: scheduler.review(base, r, at).due for r in ReviewRating}
    assert due[ReviewRating.AGAIN] < due[ReviewRating.HARD] < due[ReviewRating.GOOD]


def test_lapse_relearns_for_a_day_then_returns_to_review() -> None:
    scheduler = FsrsScheduler()
    known = scheduler.review(None, ReviewRating.GOOD, START)
    known = scheduler.review(known, ReviewRating.GOOD, known.due)
    lapsed = scheduler.review(known, ReviewRating.AGAIN, known.due)
    assert lapsed.phase == Phase.RELEARNING
    assert lapsed.due - lapsed.last_review == timedelta(days=1)

    recovered = scheduler.review(lapsed, ReviewRating.GOOD, lapsed.due)
    assert recovered.phase == Phase.REVIEW
    assert recovered.step is None
    assert recovered.due - recovered.last_review >= timedelta(days=1)


def test_new_unit_goes_straight_to_review() -> None:
    for rating in ReviewRating:
        assert FsrsScheduler().review(None, rating, START).phase == Phase.REVIEW


def test_intervals_are_whole_days() -> None:
    scheduler = FsrsScheduler()
    state = scheduler.review(None, ReviewRating.HARD, START)
    assert (state.due - START) % timedelta(days=1) == timedelta(0)


def test_retrievability_decays_over_time() -> None:
    scheduler = FsrsScheduler()
    state = scheduler.review(None, ReviewRating.GOOD, START)
    soon = scheduler.retrievability(state, START + timedelta(days=1))
    later = scheduler.retrievability(state, START + timedelta(days=30))
    assert 0 < later < soon <= 1


def test_non_utc_times_are_converted() -> None:
    scheduler = FsrsScheduler()
    local = START.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    assert scheduler.review(None, ReviewRating.GOOD, local) == scheduler.review(
        None, ReviewRating.GOOD, START
    )


def test_naive_time_is_rejected() -> None:
    with pytest.raises(ValueError):
        FsrsScheduler().review(None, ReviewRating.GOOD, datetime(2026, 10, 16))


def test_custom_parameters_change_the_schedule() -> None:
    default = FsrsScheduler().review(None, ReviewRating.GOOD, START)
    tuned = FsrsScheduler(desired_retention=0.8).review(default, ReviewRating.GOOD, default.due)
    assert tuned.due > FsrsScheduler().review(default, ReviewRating.GOOD, default.due).due


def simulate_60_days(scheduler: FsrsScheduler) -> list[MemoryState]:
    """Review whenever due over 60 days, cycling through a fixed pattern of verdicts."""
    pattern = [ReviewRating.GOOD, ReviewRating.GOOD, ReviewRating.AGAIN, ReviewRating.HARD]
    history: list[MemoryState] = []
    state = None
    at = START
    while at < START + timedelta(days=60):
        state = scheduler.review(state, pattern[len(history) % len(pattern)], at)
        history.append(state)
        at = state.due
    return history


def test_60_day_simulation_is_deterministic() -> None:
    first = simulate_60_days(FsrsScheduler())
    second = simulate_60_days(FsrsScheduler())
    assert len(first) > 5
    assert first == second


def test_only_the_adapter_imports_fsrs() -> None:
    importers = {
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if re.search(r"^\s*(import fsrs|from fsrs\b)", path.read_text("utf-8"), re.MULTILINE)
    }
    assert importers == {"core_api/domain/scheduling/fsrs_adapter.py"}
