"""T8.3a: FSRS schedule per practice question (ADR-0029, US-16 AC3/AC7/AC11, US-06 AC5).

Pure domain: apply one attempt, replay a log, remove and re-add, "thuộc" and due-today.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.mastery import PracticeRating, PracticeVerdict
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler
from core_api.domain.scheduling.practice import (
    Attempt,
    Readd,
    Removal,
    apply,
    is_due,
    is_known,
    readd,
    remove,
    replay,
)
from core_api.domain.scheduling.rating import ReviewRating
from core_api.domain.scheduling.replay import replay as card_replay

HCM = ZoneInfo("Asia/Ho_Chi_Minh")
DAY_START = 4
T0 = datetime(2026, 10, 1, 13, 0, tzinfo=UTC)


def attempt(
    verdict: PracticeVerdict = "correct",
    day: int = 0,
    active: float = 100.0,
    timing_ok: bool = True,
) -> Attempt:
    return Attempt(
        verdict=verdict,
        active_seconds=active,
        reference_seconds=100.0,
        timing_ok=timing_ok,
        at=T0 + timedelta(days=day),
    )


# US-16 lifecycle (3): the first attempt creates the state; before it there is none.
def test_first_attempt_creates_state() -> None:
    state = apply(None, attempt("correct"))
    assert state.last_verdict == "correct"
    assert state.removed_at is None
    assert state.memory.last_review == T0


# US-16 AC7: Easy only through the four-condition rule (rating_for).
def test_easy_needs_previous_correct_fast_and_timing_ok() -> None:
    first = apply(None, attempt("correct", active=50))  # no previous attempt: Good
    assert first.memory == FsrsScheduler().review(None, PracticeRating.GOOD, T0)
    fast = apply(first, attempt("correct", day=3, active=50))
    assert fast.memory == FsrsScheduler().review(
        first.memory, PracticeRating.EASY, T0 + timedelta(days=3)
    )
    slow = apply(first, attempt("correct", day=3, active=80))  # above 0.7 x reference
    assert slow.memory == FsrsScheduler().review(
        first.memory, PracticeRating.GOOD, T0 + timedelta(days=3)
    )


def test_not_measured_is_never_easy() -> None:
    first = apply(None, attempt("correct"))
    unmeasured = apply(first, attempt("correct", day=3, active=1, timing_ok=False))
    assert unmeasured.memory == FsrsScheduler().review(
        first.memory, PracticeRating.GOOD, T0 + timedelta(days=3)
    )


def test_easy_not_after_a_previous_wrong_attempt() -> None:
    wrong = apply(None, attempt("incorrect"))
    after = apply(wrong, attempt("correct", day=2, active=1))
    assert after.memory == FsrsScheduler().review(
        wrong.memory, PracticeRating.GOOD, T0 + timedelta(days=2)
    )


# US-06 AC2 also holds per question: a wrong answer comes back within a day.
def test_wrong_answer_is_due_within_a_day() -> None:
    state = apply(None, attempt("incorrect"))
    assert state.memory.due <= T0 + timedelta(days=1)


# ADR-0029: removed questions leave the schedule; re-adding resumes it. US-16 AC3.
def test_remove_stops_schedule_and_readd_resumes() -> None:
    state = apply(None, attempt("correct"))
    gone = remove(state, T0 + timedelta(days=2))
    assert gone is not None
    assert gone.due is None
    assert gone.memory == state.memory
    back = readd(gone)
    assert back.removed_at is None
    assert back.due == state.memory.due


def test_remove_before_first_attempt_has_no_state() -> None:
    assert remove(None, T0) is None


def test_attempt_on_removed_question_keeps_it_removed() -> None:
    gone = remove(apply(None, attempt("correct")), T0 + timedelta(days=1))
    assert gone is not None
    after = apply(gone, attempt("correct", day=2))
    assert after.removed_at == gone.removed_at
    assert after.due is None


# "Thuộc": retrievability >= 0.9 and last attempt correct.
def test_known_needs_recall_and_last_correct() -> None:
    state = apply(None, attempt("correct"))
    assert is_known(state, T0)  # retrievability is 1 right after answering
    assert not is_known(state, state.memory.due + timedelta(days=60))
    wrong = apply(state, attempt("incorrect", day=1))
    assert not is_known(wrong, T0 + timedelta(days=1))


# Learning-day boundary shared with cards: due by end of the learning day counts as due today.
def test_due_today_uses_the_learning_day() -> None:
    state = apply(None, attempt("incorrect"))  # due in 1 day: 2026-10-02 20:00 local
    due_local = state.memory.due.astimezone(HCM)
    before = datetime.combine(due_local.date(), time(DAY_START - 1), tzinfo=HCM)
    # 03:00 local belongs to the previous learning day, and the unit is due that same day's end
    assert is_due(state, due_local, tz=HCM, day_start_hour=DAY_START)
    assert not is_due(state, state.memory.due - timedelta(days=2), tz=HCM, day_start_hour=DAY_START)
    assert before.hour == 3


def test_removed_is_never_due() -> None:
    gone = remove(apply(None, attempt("incorrect")), T0)
    assert gone is not None
    assert not is_due(gone, T0 + timedelta(days=30), tz=HCM, day_start_hour=DAY_START)


def test_replay_of_nothing_is_none() -> None:
    assert replay([]) is None


verdicts: st.SearchStrategy[PracticeVerdict] = st.sampled_from(["correct", "partial", "incorrect"])
Raw = tuple[PracticeVerdict, int, float, bool, str]
events: st.SearchStrategy[list[Raw]] = st.lists(
    st.tuples(
        verdicts,
        st.integers(1, 20),
        st.floats(0, 400),
        st.booleans(),
        st.sampled_from(["attempt", "attempt", "attempt", "remove", "readd"]),
    ),
    max_size=15,
)


# Replay equals incremental apply, whatever the mix of attempts, removals and re-adds.
@given(events)
def test_replay_equals_incremental_apply(raw: list[Raw]) -> None:
    log: list[Attempt | Removal | Readd] = []
    state = None
    now = T0
    for verdict, gap, active, ok, kind in raw:
        now += timedelta(days=gap)
        if kind == "attempt":
            event: Attempt | Removal | Readd = Attempt(verdict, active, 100.0, ok, now)
            state = apply(state, event)
        elif kind == "remove":
            event = Removal(now)
            state = remove(state, now)
        else:
            event = Readd(now)
            state = readd(state) if state is not None else None
        log.append(event)
    assert replay(log) == state


# Card scheduling is untouched: widening the adapter type changes nothing for card ratings.
def test_card_path_unchanged() -> None:
    history = [
        (ReviewRating.GOOD, T0),
        (ReviewRating.AGAIN, T0 + timedelta(days=4)),
        (ReviewRating.HARD, T0 + timedelta(days=5)),
    ]
    exam = date(2027, 6, 1)
    expected = None
    for rating, at in history:
        expected = FsrsScheduler().review(expected, rating, at)
    got = card_replay(history, exam_day=exam, tz=HCM, day_start_hour=DAY_START)
    assert got is not None and expected is not None
    assert got.stability == expected.stability and got.difficulty == expected.difficulty
    # a practice attempt uses its own state: nothing shared with a card state
    assert apply(None, attempt("correct")).memory != got
