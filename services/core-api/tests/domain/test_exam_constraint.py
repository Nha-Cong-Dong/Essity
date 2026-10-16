"""US-06 AC3: nothing is due after the exam, and every learned unit is due at least once in the
14 learning days before it."""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.learning_day import day_bounds, learning_day
from core_api.domain.scheduling.exam_constraint import EXAM_WINDOW_DAYS, apply_exam_constraint
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, MemoryState, Phase
from core_api.domain.scheduling.rating import ReviewRating

HCM = ZoneInfo("Asia/Ho_Chi_Minh")
BERLIN = ZoneInfo("Europe/Berlin")
DAY_START = 4
TODAY = date(2026, 11, 2)


def at(day: date, hour: int = 20, tz: ZoneInfo = HCM) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=tz).astimezone(UTC)


def day_start(day: date, tz: ZoneInfo = HCM) -> datetime:
    return day_bounds(day, tz, DAY_START)[0]


def reviewed(on: date, interval_days: int) -> MemoryState:
    reviewed_at = at(on)
    return MemoryState(
        phase=Phase.REVIEW,
        step=None,
        stability=float(interval_days),
        difficulty=5.0,
        due=reviewed_at + timedelta(days=interval_days),
        last_review=reviewed_at,
    )


def constrain(state: MemoryState, exam_day: date, tz: ZoneInfo = HCM) -> MemoryState:
    return apply_exam_constraint(state, exam_day, tz, DAY_START)


def due_day(state: MemoryState, tz: ZoneInfo = HCM) -> date:
    return learning_day(state.due, tz, DAY_START)


# --- Exam tomorrow ---------------------------------------------------------------------------


def test_exam_tomorrow_brings_a_long_interval_back_to_the_exam_day() -> None:
    result = constrain(reviewed(TODAY, interval_days=30), exam_day=TODAY + timedelta(days=1))
    assert result.due == day_start(TODAY + timedelta(days=1))


def test_exam_tomorrow_never_makes_a_unit_due_again_today() -> None:
    result = constrain(reviewed(TODAY, interval_days=1), exam_day=TODAY + timedelta(days=1))
    assert due_day(result) == TODAY + timedelta(days=1)


def test_exam_tomorrow_reviewed_after_midnight_counts_as_the_previous_learning_day() -> None:
    # 01:00 on the 3rd still belongs to learning day the 2nd, so the exam on the 3rd is "tomorrow".
    state = reviewed(TODAY, interval_days=30)
    late_night = replace(state, last_review=at(TODAY + timedelta(days=1), hour=1))
    result = constrain(late_night, exam_day=TODAY + timedelta(days=1))
    assert result.due == day_start(TODAY + timedelta(days=1))


# --- Exam already passed ---------------------------------------------------------------------


def test_exam_in_the_past_leaves_fsrs_untouched() -> None:
    state = reviewed(TODAY, interval_days=30)
    assert constrain(state, exam_day=TODAY - timedelta(days=3)) == state


def test_exam_today_leaves_fsrs_untouched() -> None:
    state = reviewed(TODAY, interval_days=30)
    assert constrain(state, exam_day=TODAY) == state


# --- Unit learned yesterday, exam in 10 days ---------------------------------------------------


def test_learned_yesterday_with_exam_in_10_days_keeps_a_short_interval() -> None:
    state = reviewed(TODAY - timedelta(days=1), interval_days=3)
    assert constrain(state, exam_day=TODAY + timedelta(days=10)) == state


def test_learned_yesterday_with_exam_in_10_days_caps_a_long_interval_before_the_exam() -> None:
    exam_day = TODAY + timedelta(days=10)
    result = constrain(reviewed(TODAY - timedelta(days=1), interval_days=30), exam_day)
    assert result.due == day_start(exam_day - timedelta(days=1))


# --- The cap ---------------------------------------------------------------------------------


def test_due_on_the_exam_day_is_pulled_to_the_day_before() -> None:
    exam_day = TODAY + timedelta(days=20)
    result = constrain(reviewed(TODAY, interval_days=20), exam_day)
    assert result.due == day_start(exam_day - timedelta(days=1))


def test_due_on_the_day_before_the_exam_is_kept() -> None:
    exam_day = TODAY + timedelta(days=20)
    state = reviewed(TODAY, interval_days=19)
    assert constrain(state, exam_day) == state


def test_far_exam_does_not_change_a_due_date_before_it() -> None:
    state = reviewed(TODAY, interval_days=10)
    assert constrain(state, exam_day=TODAY + timedelta(days=60)) == state


def test_only_due_changes() -> None:
    state = reviewed(TODAY, interval_days=90)
    result = constrain(state, exam_day=TODAY + timedelta(days=20))
    assert result != state
    assert replace(result, due=state.due) == state


def test_cap_uses_the_users_time_zone() -> None:
    state = reviewed(TODAY, interval_days=90)
    exam_day = TODAY + timedelta(days=20)
    result = constrain(state, exam_day, tz=BERLIN)
    assert result.due == day_start(exam_day - timedelta(days=1), tz=BERLIN)


def test_relearning_unit_keeps_its_one_day_step() -> None:
    lapsed = replace(reviewed(TODAY, interval_days=1), phase=Phase.RELEARNING, step=0)
    assert constrain(lapsed, exam_day=TODAY + timedelta(days=5)) == lapsed


# --- Properties ------------------------------------------------------------------------------


@given(
    reviewed_on=st.dates(min_value=date(2026, 1, 1), max_value=date(2028, 12, 31)),
    hour=st.integers(min_value=0, max_value=23),
    interval_days=st.integers(min_value=1, max_value=400),
    exam_offset=st.integers(min_value=-30, max_value=200),
    tz=st.sampled_from([HCM, BERLIN, ZoneInfo("America/New_York")]),
)
def test_constraint_invariants(
    reviewed_on: date, hour: int, interval_days: int, exam_offset: int, tz: ZoneInfo
) -> None:
    reviewed_at = at(reviewed_on, hour, tz)
    state = MemoryState(
        phase=Phase.REVIEW,
        step=None,
        stability=1.0,
        difficulty=5.0,
        due=reviewed_at + timedelta(days=interval_days),
        last_review=reviewed_at,
    )
    review_day = learning_day(reviewed_at, tz, DAY_START)
    exam_day = review_day + timedelta(days=exam_offset)

    result = apply_exam_constraint(state, exam_day, tz, DAY_START)

    assert replace(result, due=state.due) == state  # only due may change
    assert result.due <= state.due  # never pushed later
    if exam_day <= review_day:
        assert result == state
        return
    latest = max(exam_day - timedelta(days=1), review_day + timedelta(days=1))
    assert learning_day(result.due, tz, DAY_START) <= latest  # never after the exam
    if result != state:
        assert result.due == day_bounds(latest, tz, DAY_START)[0]


def simulate_until_exam(first_review: date, exam_day: date) -> list[MemoryState]:
    """Review whenever due, always correctly, applying the constraint after every review."""
    scheduler = FsrsScheduler()
    history: list[MemoryState] = []
    state = None
    reviewed_at = at(first_review)
    while learning_day(reviewed_at, HCM, DAY_START) < exam_day:
        state = constrain(scheduler.review(state, ReviewRating.GOOD, reviewed_at), exam_day)
        history.append(state)
        reviewed_at = max(state.due, reviewed_at + timedelta(days=1))
    return history


def test_simulation_long_before_exam_is_due_in_the_window_and_never_after() -> None:
    exam_day = TODAY + timedelta(days=120)
    history = simulate_until_exam(TODAY, exam_day)
    due_days = [due_day(s) for s in history]
    window = (exam_day - timedelta(days=EXAM_WINDOW_DAYS), exam_day - timedelta(days=1))
    assert all(d <= exam_day for d in due_days)
    assert any(window[0] <= d <= window[1] for d in due_days)


def test_simulation_subject_created_5_days_before_exam_still_never_due_after() -> None:
    # PRD §7.4: the 14-day window cannot be met in full; the unit still comes back before the exam.
    exam_day = TODAY + timedelta(days=5)
    history = simulate_until_exam(TODAY, exam_day)
    assert all(due_day(s) <= exam_day - timedelta(days=1) for s in history[:-1])
    assert all(due_day(s) <= exam_day for s in history)
