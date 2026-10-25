"""T2.6: memory_state is a cache; replaying review_log through the same step the live path uses
(FSRS, then the exam constraint) rebuilds it field for field. US-01 AC3: a later exam date moves
due dates back out only through a replay, because the constraint only ever pulls them in."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from core_api.domain.learning_day import learning_day
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler
from core_api.domain.scheduling.rating import ReviewRating
from core_api.domain.scheduling.replay import replay, schedule_review

HCM = ZoneInfo("Asia/Ho_Chi_Minh")
DAY_START = 4
SCHEDULER = FsrsScheduler()


def at(day: date, hour: int = 20) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=HCM).astimezone(UTC)


HISTORY = [
    (ReviewRating.GOOD, at(date(2026, 10, 1))),
    (ReviewRating.GOOD, at(date(2026, 10, 4))),
    (ReviewRating.AGAIN, at(date(2026, 10, 12))),
    (ReviewRating.HARD, at(date(2026, 10, 13))),
    (ReviewRating.GOOD, at(date(2026, 10, 20))),
]


def test_a_unit_never_reviewed_has_no_state() -> None:
    assert replay([], exam_day=date(2026, 12, 15), tz=HCM, day_start_hour=DAY_START) is None


# Red when: replay and the live path drift apart (a different order of FSRS and the exam cap, or
# the cap left out), so a rebuilt cache differs from the one reviews wrote.
def test_replay_gives_the_state_the_live_reviews_wrote_field_for_field() -> None:
    exam = date(2026, 11, 10)
    live = None
    for rating, reviewed_at in HISTORY:
        live = schedule_review(
            live, rating, reviewed_at, exam_day=exam, tz=HCM, day_start_hour=DAY_START
        )
    assert replay(HISTORY, exam_day=exam, tz=HCM, day_start_hour=DAY_START) == live


def test_the_live_step_caps_due_at_the_day_before_the_exam() -> None:
    exam = date(2026, 10, 25)
    state = replay(HISTORY, exam_day=exam, tz=HCM, day_start_hour=DAY_START)
    assert state is not None
    assert learning_day(state.due, HCM, DAY_START) == date(2026, 10, 24)
    uncapped = replay(HISTORY, exam_day=date(2027, 6, 1), tz=HCM, day_start_hour=DAY_START)
    assert uncapped is not None
    assert uncapped.due > state.due
    # Only due is capped: the memory model is the same.
    assert (uncapped.stability, uncapped.difficulty) == (state.stability, state.difficulty)


# US-01 AC3. Red when: moving the exam later keeps the old capped due date.
def test_us01_ac3_a_later_exam_moves_due_back_out() -> None:
    near = replay(HISTORY, exam_day=date(2026, 10, 25), tz=HCM, day_start_hour=DAY_START)
    far = replay(HISTORY, exam_day=date(2027, 1, 20), tz=HCM, day_start_hour=DAY_START)
    assert near is not None and far is not None
    assert far.due > near.due + timedelta(days=1)


# Red when: a history read in the wrong order is replayed silently, building a wrong state.
def test_reviews_out_of_order_are_refused() -> None:
    with pytest.raises(ValueError, match="order"):
        replay(
            list(reversed(HISTORY)), exam_day=date(2026, 12, 15), tz=HCM, day_start_hour=DAY_START
        )


def test_the_same_scheduler_parameters_are_used_as_the_live_path() -> None:
    exam = date(2027, 1, 20)
    rebuilt = replay(HISTORY, exam_day=exam, tz=HCM, day_start_hour=DAY_START)
    state = None
    for rating, reviewed_at in HISTORY:
        state = SCHEDULER.review(state, rating, reviewed_at)
    assert rebuilt == state  # far exam: the cap changes nothing
