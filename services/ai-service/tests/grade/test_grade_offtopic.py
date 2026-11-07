"""E-18: an off-topic answer is incorrect, never partial."""

import json
from typing import Any

from ai_service.tasks.grade import (
    OFF_TOPIC_MISSING,
    OUTPUT_SCHEMA,
    Labels,
    check_output,
    load_prompt,
)
from ai_service.tasks.grade_models import GradeRequest
from tests.grade.helpers import anchor, grade_body, unit

REQUEST = GradeRequest.model_validate(grade_body(units=[unit("Hoán vị", anchor())]))
LABELS = Labels.of(REQUEST)


def output(**overrides: Any) -> str:
    good: dict[str, Any] = {
        "units": [{"unit": "U1", "verdict": "partial"}],
        "missing": ["Thiếu công thức"],
        "anchors_used": ["U1.A1"],
        "understanding": 1,
    }
    return json.dumps({**good, **overrides}, ensure_ascii=False)


def test_prompt_has_the_off_topic_rule() -> None:
    text = load_prompt().text
    assert "Off-topic" in text
    assert "off_topic" in text
    assert "Never give `partial`" in text


def test_off_topic_is_in_the_schema_and_output_without_it_still_passes() -> None:
    assert OUTPUT_SCHEMA["properties"]["off_topic"] == {"type": "boolean"}
    assert "off_topic" in OUTPUT_SCHEMA["required"]
    assert check_output(output(), LABELS).overall == "partial"  # old-shape output


def test_off_topic_flag_forces_incorrect() -> None:
    outcome = check_output(output(off_topic=True), LABELS)
    assert outcome.overall == "incorrect"
    assert [u.verdict for u in outcome.units] == ["incorrect"]
    assert outcome.understanding is None
    assert outcome.anchors_used == []
    assert outcome.missing == ["Thiếu công thức"]


def test_off_topic_with_empty_missing_gets_a_note() -> None:
    outcome = check_output(output(off_topic=True, missing=[], understanding=None), LABELS)
    assert outcome.missing == [OFF_TOPIC_MISSING]


def test_without_the_flag_nothing_changes() -> None:
    assert check_output(output(), LABELS).overall == "partial"
    assert check_output(output(off_topic=False), LABELS).overall == "partial"
