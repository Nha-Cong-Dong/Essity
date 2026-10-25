"""T2.12-b: R03, the model's output is checked by code, never trusted (risk register R03).

Each rule has a test that feeds a broken output and expects `OutputViolation`.
"""

import json
from typing import Any

import pytest

from ai_service.tasks.grade import Labels, OutputViolation, check_output
from ai_service.tasks.grade_models import GradeRequest
from tests.grade.helpers import anchor, grade_body, unit

TWO_UNITS = GradeRequest.model_validate(
    grade_body(units=[unit("Bắt tay", anchor(), anchor()), unit("Flow control", anchor())])
)
LABELS = Labels.of(TWO_UNITS)


def output(**overrides: Any) -> str:
    good: dict[str, Any] = {
        "units": [{"unit": "U1", "verdict": "correct"}, {"unit": "U2", "verdict": "incorrect"}],
        "missing": ["Chưa nói về cửa sổ trượt"],
        "anchors_used": ["U1.A1", "U2.A1"],
        "understanding": 2,
    }
    return json.dumps({**good, **overrides}, ensure_ascii=False)


def violation(text: str) -> str:
    with pytest.raises(OutputViolation) as raised:
        check_output(text, LABELS)
    return raised.value.rule


def test_r03_good_output_passes_and_maps_labels_back_to_ids() -> None:
    outcome = check_output(output(), LABELS)
    unit_ids = [u.unit_id for u in TWO_UNITS.units]
    assert [(v.unit_id, v.verdict) for v in outcome.units] == [
        (unit_ids[0], "correct"),
        (unit_ids[1], "incorrect"),
    ]
    assert outcome.anchors_used == [
        TWO_UNITS.units[0].anchors[0].anchor_id,
        TWO_UNITS.units[1].anchors[0].anchor_id,
    ]
    assert (outcome.overall, outcome.understanding) == ("partial", 2)


# Rule 1: the set of units out is exactly the set in.
@pytest.mark.parametrize(
    "units",
    [
        [{"unit": "U1", "verdict": "correct"}],  # one missing
        [
            {"unit": "U1", "verdict": "correct"},
            {"unit": "U2", "verdict": "correct"},
            {"unit": "U3", "verdict": "correct"},  # one the request does not have
        ],
        [],
    ],
)
def test_r03_1_unit_set_must_equal_the_request(units: list[dict[str, str]]) -> None:
    # Red when: a unit can be dropped or invented, and core writes grade_unit rows for units
    # the question does not test (or none for one it does).
    assert violation(output(units=units, missing=["x"], understanding=2)) == "units"


# Rule 2: one verdict per unit.
@pytest.mark.parametrize("second", ["correct", "incorrect"])
def test_r03_2_each_unit_has_exactly_one_verdict(second: str) -> None:
    units = [
        {"unit": "U1", "verdict": "correct"},
        {"unit": "U1", "verdict": second},
        {"unit": "U2", "verdict": "incorrect"},
    ]
    assert violation(output(units=units)) == "units"


# Rule 3: anchors used were sent, belong to the request's units, and appear once.
@pytest.mark.parametrize(
    "anchors", [["U1.A3"], ["U3.A1"], ["U1.A1", "U1.A1"]], ids=["unsent", "other-unit", "twice"]
)
def test_r03_3_anchors_used_are_among_those_sent(anchors: list[str]) -> None:
    # Red when: the result links to a source that was never read for this question (AC2).
    assert violation(output(anchors_used=anchors)) == "anchors_used"


@pytest.mark.parametrize("anchors", [[], ["U2.A1"]], ids=["none", "only-of-the-wrong-unit"])
def test_r03_3b_a_right_answer_names_a_source_of_a_right_unit(anchors: list[str]) -> None:
    # Red when: a correct or partial result links to no source of what it judged right, and
    # the result screen has nothing to show under "nguồn" (AC2; review 🟡1, rule 3b).
    assert violation(output(anchors_used=anchors)) == "anchors_used"


def test_r03_3b_a_wrong_answer_may_name_no_source() -> None:
    units = [{"unit": "U1", "verdict": "incorrect"}, {"unit": "U2", "verdict": "incorrect"}]
    outcome = check_output(output(units=units, anchors_used=[], understanding=None), LABELS)
    assert (outcome.overall, outcome.anchors_used) == ("incorrect", [])


def test_r03_3b_one_source_of_a_right_unit_is_enough() -> None:
    assert len(check_output(output(anchors_used=["U1.A2"]), LABELS).anchors_used) == 1


# Rule 4: overall is derived by the code.
@pytest.mark.parametrize(
    ("verdicts", "overall"),
    [
        (("correct", "correct"), "correct"),
        (("incorrect", "incorrect"), "incorrect"),
        (("correct", "incorrect"), "partial"),
        (("partial", "partial"), "partial"),
        (("correct", "partial"), "partial"),
    ],
)
def test_r03_4_overall_is_derived_from_the_unit_verdicts(
    verdicts: tuple[str, str], overall: str
) -> None:
    units = [{"unit": f"U{i}", "verdict": v} for i, v in enumerate(verdicts, start=1)]
    missing = [] if overall == "correct" else ["x"]
    understanding = None if overall == "incorrect" else 1
    outcome = check_output(
        output(units=units, missing=missing, understanding=understanding), LABELS
    )
    assert outcome.overall == overall


def test_r03_4_overall_from_the_model_is_refused() -> None:
    # Red when: the model may state overall itself and contradict its unit verdicts.
    assert violation(output(overall="correct")) == "schema"


# Rule 5: understanding (1..3) when right, null when wrong (core's understanding_when_right).
def test_r03_5_understanding_is_null_when_overall_is_incorrect() -> None:
    units = [{"unit": "U1", "verdict": "incorrect"}, {"unit": "U2", "verdict": "incorrect"}]
    assert violation(output(units=units, understanding=1)) == "understanding"


@pytest.mark.parametrize("understanding", [None, 0, 4])
def test_t212_understanding_scale(understanding: int | None) -> None:
    # B1, 🟡h: 1..3 is required when correct or partial; 0, 4 and null are refused.
    assert violation(output(understanding=understanding)) in {"understanding", "schema"}


@pytest.mark.parametrize("understanding", [1, 2, 3])
def test_t212_understanding_scale_accepts_one_to_three(understanding: int) -> None:
    assert check_output(output(understanding=understanding), LABELS).understanding == understanding


# Rule 6: 1..3 missing points when not correct, none when correct; each short and not blank.
@pytest.mark.parametrize(
    "missing",
    [[], ["a", "b", "c", "d"], ["   "], ["x" * 201]],
    ids=["none-when-wrong", "four", "blank", "too-long"],
)
def test_r03_6_missing_points_are_bounded(missing: list[str]) -> None:
    assert violation(output(missing=missing)) == "missing"


def test_r03_6_missing_is_empty_when_correct() -> None:
    units = [{"unit": "U1", "verdict": "correct"}, {"unit": "U2", "verdict": "correct"}]
    assert violation(output(units=units, missing=["x"], understanding=3)) == "missing"


def test_r03_6_missing_at_the_limit_is_accepted() -> None:
    outcome = check_output(output(missing=["a" * 200, "b", "c"]), LABELS)
    assert outcome.missing == ["a" * 200, "b", "c"]


# Rule 7: broken JSON, extra or missing fields, wrong types.
@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        '{"units": [',
        "[]",
        output()[:-1],
        output(extra="field"),
        json.dumps({"units": [], "missing": []}),
        output(units=[{"unit": "U1", "verdict": "maybe"}, {"unit": "U2", "verdict": "correct"}]),
        output(units=[{"unit": "U1", "verdict": "correct", "why": "x"}]),
        output(understanding="2"),
        output(understanding=True),
    ],
)
def test_r03_7_output_outside_the_schema_is_refused(text: str) -> None:
    assert violation(text) in {"schema", "units"}


def test_r03_violation_does_not_carry_the_output() -> None:
    # The rule name is safe to log and store; the output itself is not (ADR-0013).
    with pytest.raises(OutputViolation) as raised:
        check_output('{"secret-output": 1}', LABELS)
    assert "secret-output" not in str(raised.value)
