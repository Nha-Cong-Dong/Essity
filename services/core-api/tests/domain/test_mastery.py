"""T8.6a (v2 design §8.2, Q-C): mastery per question type and practice rating. Pure."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.mastery import (
    PracticeRating,
    PracticeVerdict,
    TypeAttempt,
    active_seconds,
    is_learned,
    is_timing_ok,
    mastery,
    rating_for,
    reference_seconds,
)


def att(verdict: PracticeVerdict, secs: float | None = None, ok: bool = False) -> TypeAttempt:
    return TypeAttempt(verdict, secs, ok)


def test_fewer_than_three_attempts_is_not_enough_data():
    assert mastery([]) is None
    assert mastery([att("correct"), att("correct")]) is None


def test_mean_of_scores():
    assert mastery([att("correct"), att("partial"), att("incorrect")]) == 0.5


def test_only_last_ten_count():
    old = [att("incorrect")] * 5
    recent = [att("correct")] * 10
    assert mastery(old + recent) == 1.0
    assert mastery(recent + old) == pytest.approx(0.5)


def test_reference_defaults_to_60s_per_idea():
    assert reference_seconds(3, []) == 180
    assert reference_seconds(0, []) == 60
    four = [att("correct", 10, True)] * 4
    assert reference_seconds(2, four) == 120


def test_reference_is_median_after_five_correct_timed():
    attempts = [att("correct", t, True) for t in [10, 20, 30, 40, 50]]
    assert reference_seconds(3, attempts) == 30


def test_reference_ignores_untimed_wrong_and_unmeasured():
    attempts = [att("correct", 10, True)] * 4 + [
        att("correct", 5, False),
        att("partial", 5, True),
        att("correct", None, True),
    ]
    assert reference_seconds(1, attempts) == 60


def test_active_subtracts_hidden_time():
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    assert active_seconds(t0, t0 + timedelta(seconds=100), 30_000) == 70


def test_timing_ok_rules():
    assert is_timing_ok(50, 0, 60)
    assert not is_timing_ok(50, 1, 60)  # hidden tab
    assert is_timing_ok(180, 0, 60)  # exactly 3x
    assert not is_timing_ok(180.1, 0, 60)
    assert not is_timing_ok(-1, 0, 60)  # clock skew


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ("incorrect", PracticeRating.AGAIN),
        ("partial", PracticeRating.HARD),
        ("correct", PracticeRating.GOOD),
    ],
)
def test_base_rating_map(verdict: PracticeVerdict, expected: PracticeRating):
    assert rating_for(verdict, 1000, 60, None, False) == expected


def test_easy_needs_every_condition():
    assert rating_for("correct", 42, 60, "correct", True) == PracticeRating.EASY  # exactly 0.7x
    assert rating_for("correct", 43, 60, "correct", True) == PracticeRating.GOOD
    assert rating_for("correct", 10, 60, "partial", True) == PracticeRating.GOOD
    assert rating_for("correct", 10, 60, None, True) == PracticeRating.GOOD
    assert rating_for("correct", 10, 60, "correct", False) == PracticeRating.GOOD


@pytest.mark.parametrize("verdict", ["partial", "incorrect"])
def test_fast_but_not_correct_is_never_easy(verdict: PracticeVerdict):
    assert rating_for(verdict, 1, 60, "correct", True) != PracticeRating.EASY


def test_learned():
    assert is_learned(0.9, "correct")
    assert not is_learned(0.89, "correct")
    assert not is_learned(0.99, "partial")
    assert not is_learned(0.99, None)


verdicts: st.SearchStrategy[PracticeVerdict] = st.sampled_from(["correct", "partial", "incorrect"])


@given(st.lists(verdicts.map(att), max_size=30))
def test_property_mastery_bounded_and_none_only_below_three(attempts: list[TypeAttempt]):
    m = mastery(attempts)
    assert (m is None) == (len(attempts) < 3)
    if m is not None:
        assert 0 <= m <= 1


@given(verdicts, st.floats(0, 1e4), st.floats(1, 1e3), st.one_of(st.none(), verdicts))
def test_property_not_timing_ok_is_never_easy(
    verdict: PracticeVerdict, active: float, ref: float, prev: PracticeVerdict | None
):
    assert rating_for(verdict, active, ref, prev, False) != PracticeRating.EASY
