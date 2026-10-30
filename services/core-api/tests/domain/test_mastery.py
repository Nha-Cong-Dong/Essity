"""T8.6a (v2 design §8.2, Q-C): mastery per question type and practice rating. Pure."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.mastery import (
    BANNED_WORDS,
    DEFAULT_CONFIG,
    MasteryConfig,
    PracticeRating,
    PracticeVerdict,
    Reference,
    Sensitivity,
    TypeAttempt,
    active_seconds,
    is_learned,
    is_timing_ok,
    mastery,
    mastery_line,
    rating_for,
    reference,
    reference_seconds,
    sensitivity,
    sensitivity_line,
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
    # US-16 AC6: median, not mean (asymmetric data: median 20, mean 40)
    attempts = [att("correct", t, True) for t in [10, 15, 20, 25, 130]]
    assert reference_seconds(3, attempts) == 20


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


# --- T8.6b: config, ref_origin, sensitivity, copy ---


def test_config_is_versioned_and_defaults_match_us16():  # US-16 AC4, AC5, AC6, AC7
    c = DEFAULT_CONFIG
    assert c.version == "v1"
    assert (c.window, c.min_attempts, c.seconds_per_idea, c.min_timed_correct) == (10, 3, 60.0, 5)
    assert (c.slow_factor, c.easy_factor, c.learned_retrievability) == (3.0, 0.7, 0.9)


def test_config_changes_formula_without_caller_change():  # US-16 (cấu hình có phiên bản)
    c = MasteryConfig(version="v2", window=2, min_attempts=2)
    assert mastery([att("incorrect"), att("correct"), att("correct")], c) == 1.0
    assert mastery([att("correct")], c) is None
    assert reference_seconds(2, [], MasteryConfig(version="v2", seconds_per_idea=30)) == 60
    assert not is_timing_ok(61, 0, 20, MasteryConfig(version="v2", slow_factor=2))
    assert (
        rating_for(
            "correct", 50, 100, "correct", True, MasteryConfig(version="v2", easy_factor=0.5)
        )
        == PracticeRating.EASY
    )
    assert is_learned(0.8, "correct", MasteryConfig(version="v2", learned_retrievability=0.8))


def test_ref_origin_default_then_learner():  # US-16 AC6
    four = [att("correct", 10, True)] * 4
    assert reference(2, four) == Reference(120, "default")
    five = four + [att("correct", 10, True)]
    assert reference(2, five) == Reference(10, "learner")
    assert reference(2, []).origin == "default"


def test_sensitivity_needs_three_timed_attempts():  # US-16 AC8
    two = [att("correct", 10, True)] * 2
    assert sensitivity(two, 60) == Sensitivity.NOT_ENOUGH_DATA
    assert sensitivity([att("correct", 10, False)] * 5, 60) == Sensitivity.NOT_ENOUGH_DATA
    assert sensitivity([att("correct", 10, True)] * 3, 60) == Sensitivity.FASTER


def test_sensitivity_boundaries():  # US-16 AC8
    def ratio(r: float) -> Sensitivity:
        return sensitivity([att("correct", 60 * r, True)] * 3, 60)

    assert ratio(0.79) == Sensitivity.FASTER
    assert ratio(0.8) == Sensitivity.NEAR
    assert ratio(1.25) == Sensitivity.NEAR
    assert ratio(1.26) == Sensitivity.SLOWER


def test_sensitivity_ignores_not_timing_ok_and_uses_window():  # US-16 AC5, AC8
    junk = [att("correct", 9999, False)] * 5
    assert sensitivity(junk + [att("correct", 60, True)] * 3, 60) == Sensitivity.NEAR
    old = [att("incorrect", 600, True)] * 5
    recent = [att("correct", 60, True)] * 10
    assert sensitivity(old + recent, 60) == Sensitivity.NEAR


def test_sensitivity_uses_median_of_asymmetric_times():  # US-16 AC8
    attempts = [att("correct", t, True) for t in [30, 30, 300]]
    assert sensitivity(attempts, 60) == Sensitivity.FASTER  # median 30, mean 120


def test_mastery_line_copy():  # US-16 AC4
    assert mastery_line(None) == "chưa đủ dữ liệu"
    assert mastery_line(0.7) == "đúng 7 trên 10 lần gần nhất"
    assert mastery_line(0.5, n=4) == "đúng 2 trên 4 lần gần nhất"


@pytest.mark.parametrize(
    ("s", "ref", "text"),
    [
        (Sensitivity.NOT_ENOUGH_DATA, 180, "chưa đủ dữ liệu"),
        (Sensitivity.FASTER, 180, "nhanh hơn mốc, khoảng 3 phút mỗi câu"),
        (Sensitivity.NEAR, 90, "gần mốc, khoảng 1,5 phút mỗi câu"),
        (Sensitivity.SLOWER, 45, "chậm hơn mốc, khoảng 45 giây mỗi câu"),
    ],
)
def test_sensitivity_line_copy(s: Sensitivity, ref: float, text: str):  # US-16 AC8
    assert sensitivity_line(s, ref) == text


def _has_banned(text: str) -> bool:
    return any(
        re.search(rf"(?<![^\W\d_]){re.escape(w)}(?![^\W\d_])", text, re.IGNORECASE)
        for w in BANNED_WORDS
    )


def test_copy_has_no_banned_words():  # US-16 AC8
    lines = [mastery_line(None), mastery_line(0.0), mastery_line(1.0)]
    lines += [sensitivity_line(s, r) for s in Sensitivity for r in (30, 90, 600)]
    assert not any(_has_banned(x) for x in lines)


def test_banned_regex_is_unicode_safe():  # US-16 AC8
    assert _has_banned("Bạn thật chậm chạp")
    assert _has_banned("CHẬM CHẠP.")
    assert not _has_banned("nhanh hơn mốc")
    assert not _has_banned("tệp")  # prefix of a longer word is fine
    assert _has_banned("quá yếu!")
