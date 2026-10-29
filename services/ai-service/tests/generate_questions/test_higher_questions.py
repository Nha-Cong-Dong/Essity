"""T5.1: level-2 and level-3 questions, validated by code (US-04b AC1)."""

import uuid
from typing import Any

import pytest

from ai_service.tasks.generate_questions import (
    OutputViolation,
    QuestionsInvalidError,
    check_higher_questions,
    generate_higher_questions,
    generate_questions,
)

from .helpers import U1, U2, FakeAsk, full_output, higher_full, higher_json, output, request

U3 = uuid.UUID("33333333-3333-3333-3333-333333333333")
LABELS = {"U1": U1, "U2": U2}


def _ok() -> list[dict[str, Any]]:
    return [higher_json(2, "U1"), higher_json(2, "U2"), higher_json(3, "U1", "U2")]


def test_level2_per_unit_and_level3_with_two_units() -> None:  # US-04b AC1
    ask = FakeAsk(higher_full())
    result = generate_higher_questions(request(2), ask)
    assert [q.level for q in result.questions] == [2, 2, 3]
    assert result.questions[0].unit_ids == [U1]
    assert result.questions[2].unit_ids == [U1, U2]
    assert all(q.reference_answer and q.rubric for q in result.questions)
    assert "prompt v2" in ask.prompts[0].system


def test_level3_with_one_unit_is_refused_and_retried() -> None:  # US-04b AC1
    bad = output(higher_json(2, "U1"), higher_json(2, "U2"), higher_json(3, "U1"))
    ask = FakeAsk(bad, higher_full())
    result = generate_higher_questions(request(2), ask)
    assert len(ask.prompts) == 2
    assert [q.level for q in result.questions] == [2, 2, 3]


def test_level3_repeating_one_label_counts_as_one_unit() -> None:  # US-04b AC1
    bad = output(higher_json(2, "U1"), higher_json(2, "U2"), higher_json(3, "U1", "U1"))
    with pytest.raises(OutputViolation) as e:
        check_higher_questions(bad, LABELS)
    assert e.value.rule == "level3_units"


def test_always_invalid_raises() -> None:
    with pytest.raises(QuestionsInvalidError):
        generate_higher_questions(request(2), FakeAsk(output(higher_json(3, "U1"))))


def test_level2_with_three_units_refused() -> None:
    bad = output(higher_json(2, "U1", "U2", "U3"))
    with pytest.raises(OutputViolation) as e:
        check_higher_questions(bad, {**LABELS, "U3": U3})
    assert e.value.rule == "level2_units"


def test_unit_without_level2_refused() -> None:
    bad = output(higher_json(2, "U1"), higher_json(3, "U1", "U2"))
    with pytest.raises(OutputViolation) as e:
        check_higher_questions(bad, LABELS)
    assert e.value.rule == "unit_uncovered"


def test_missing_level3_refused_with_two_units() -> None:
    bad = output(higher_json(2, "U1"), higher_json(2, "U2"))
    with pytest.raises(OutputViolation) as e:
        check_higher_questions(bad, LABELS)
    assert e.value.rule == "level3_missing"


def test_single_unit_needs_no_level3() -> None:
    result = generate_higher_questions(request(1), FakeAsk(output(higher_json(2, "U1"))))
    assert [q.level for q in result.questions] == [2]


def test_unknown_label_dropped_by_name_only() -> None:
    result = check_higher_questions(output(higher_json(3, "U1", "U9"), *_ok()), LABELS)
    assert [d.reason for d in result.dropped] == ["unknown_unit"]
    assert [q.level for q in result.questions] == [2, 2, 3]


def test_level_other_than_2_or_3_is_schema_violation() -> None:
    with pytest.raises(OutputViolation) as e:
        check_higher_questions(output(higher_json(1, "U1")), LABELS)
    assert e.value.rule == "schema"


def test_empty_request_makes_no_call() -> None:
    ask = FakeAsk("x")
    assert generate_higher_questions(request(0), ask).questions == []
    assert ask.prompts == []


def test_level1_api_unchanged() -> None:
    result = generate_questions(request(2), FakeAsk(full_output(2)))
    assert {q.level for q in result.questions} == {1}
