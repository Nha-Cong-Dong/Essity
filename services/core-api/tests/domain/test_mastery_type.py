"""T8.6b (US-16 AC4, AC5, AC6, AC8): per-type summary and the versioned formula file. Pure."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.mastery import (
    DEFAULT_CONFIG,
    MasteryConfig,
    PracticeVerdict,
    Sensitivity,
    TypeAttempt,
    has_banned_word,
)
from core_api.domain.mastery_type import (
    UnknownFormulaVersionError,
    load_config,
    load_config_from,
    summarize,
)


def att(v: PracticeVerdict, secs: float | None = None, ok: bool = False) -> TypeAttempt:
    return TypeAttempt(v, secs, ok)


def test_shipped_v1_equals_default_config():  # US-16 AC4-AC7
    assert load_config() == DEFAULT_CONFIG
    assert load_config("v1").version == "v1"


def test_unknown_version_is_refused():
    with pytest.raises(UnknownFormulaVersionError):
        load_config("v99")


def test_new_formula_version_needs_no_code():  # US-16 (config has a version)
    doc = {
        "current": "v2",
        "versions": {"v1": {}, "v2": {"window": 5, "min_attempts": 2, "slow_factor": 2.0}},
    }
    c = load_config_from(json.dumps(doc))
    assert (c.version, c.window, c.min_attempts, c.slow_factor) == ("v2", 5, 2, 2.0)
    assert c.seconds_per_idea == DEFAULT_CONFIG.seconds_per_idea


def test_unknown_key_in_formula_file_is_refused():
    with pytest.raises(ValueError):
        load_config_from(json.dumps({"current": "v1", "versions": {"v1": {"windoww": 3}}}))


def test_under_three_attempts_not_enough_data():  # US-16 AC4
    s = summarize(120, "default", [att("correct"), att("correct")])
    assert s.mastery is None
    assert s.mastery_line == "chưa đủ dữ liệu"
    assert s.sensitivity == Sensitivity.NOT_ENOUGH_DATA


def test_three_attempts_line_says_two_of_three():  # US-16 AC4
    s = summarize(120, "default", [att("correct"), att("correct"), att("incorrect")])
    assert s.attempts_counted == 3
    assert s.mastery_line == "đúng 2 trên 3 lần gần nhất"


def test_counted_attempts_capped_at_window():  # US-16 AC4
    s = summarize(120, "default", [att("correct")] * 14)
    assert s.attempts_counted == 10
    assert s.mastery_line == "đúng 10 trên 10 lần gần nhất"


def test_reference_switches_to_learner_median_after_five_correct():  # US-16 AC6
    four = [att("correct", 30, True)] * 4
    s4 = summarize(120, "rubric", four)
    assert (s4.reference_seconds, s4.ref_origin) == (120, "rubric")
    five = [att("correct", t, True) for t in (10, 15, 20, 25, 130)]
    s5 = summarize(120, "rubric", five)
    assert (s5.reference_seconds, s5.ref_origin) == (20, "learner_median")


def test_user_set_reference_is_kept():  # US-16 AC6 (spec: ref_origin "user")
    five = [att("correct", 10, True)] * 5
    s = summarize(90, "user", five)
    assert (s.reference_seconds, s.ref_origin) == (90, "user")


def test_sensitivity_uses_only_timing_ok():  # US-16 AC5, AC8
    attempts = [att("correct", 10, True)] * 3 + [att("correct", 1000, False)] * 5
    s = summarize(100, "default", attempts)
    assert s.sensitivity == Sensitivity.FASTER
    assert not has_banned_word(s.sensitivity_line)


def test_lines_are_neutral_for_every_outcome():  # US-16 AC8
    s = summarize(60, "default", [att("incorrect")] * 3)
    assert not has_banned_word(s.mastery_line)
    assert not has_banned_word(s.sensitivity_line)


verdicts = st.sampled_from(["correct", "partial", "incorrect"])
attempts_st = st.lists(
    st.builds(
        TypeAttempt,
        verdicts,
        st.one_of(st.none(), st.floats(0, 5000, allow_nan=False)),
        st.booleans(),
    ),
    max_size=30,
)


@given(attempts_st, st.integers(1, 3600))
def test_property_summary_is_consistent(attempts: list[TypeAttempt], base: int):  # US-16 AC4, AC8
    s = summarize(base, "default", attempts)
    assert (s.mastery is None) == (len(attempts) < DEFAULT_CONFIG.min_attempts)
    assert s.attempts_counted == min(len(attempts), DEFAULT_CONFIG.window)
    assert s.reference_seconds > 0
    assert not has_banned_word(s.mastery_line)
    assert not has_banned_word(s.sensitivity_line)
    if s.mastery is not None:
        assert 0 <= s.mastery <= 1


def test_config_object_is_frozen():
    with pytest.raises(AttributeError):
        DEFAULT_CONFIG.window = 3  # type: ignore[misc]
    assert isinstance(DEFAULT_CONFIG, MasteryConfig)
