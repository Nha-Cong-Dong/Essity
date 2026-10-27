import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evals.grade.schema import EvalCase, load_cases
from tests.evals.helpers import case_dict


def test_case_parses() -> None:
    case = EvalCase.model_validate(case_dict())
    assert case.expected.overall == "correct"


def test_case_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate(case_dict(extra="x"))


def test_units_expected_length_matches() -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate(
            case_dict(expected={"overall": "correct", "units": ["correct", "correct"]})
        )


def test_expected_overall_must_follow_units() -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate(case_dict(expected={"overall": "correct", "units": ["partial"]}))


def test_expected_verdict_must_be_known() -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate(case_dict(expected={"overall": "right", "units": ["right"]}))


@pytest.mark.parametrize("category", ["paraphrase", "mixed_lang", "typo"])
def test_right_idea_case_must_expect_correct(category: str) -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate(
            case_dict(category=category, expected={"overall": "partial", "units": ["partial"]})
        )


def test_injection_case_cannot_expect_correct() -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate(case_dict(category="injection"))


def test_level_in_range() -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate(case_dict(level=4))


def _write(path: Path, cases: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
    return path


def test_dataset_rejects_duplicate_id(tmp_path: Path) -> None:
    path = _write(tmp_path / "d.jsonl", [case_dict("a"), case_dict("a")])
    with pytest.raises(ValueError, match="duplicate"):
        load_cases(path)


def test_dataset_error_names_the_line_not_the_text(tmp_path: Path) -> None:
    path = _write(tmp_path / "d.jsonl", [case_dict("a"), {"id": "b", "answer": "SECRET-TEXT"}])
    with pytest.raises(ValueError, match="line 2") as info:
        load_cases(path)
    assert "SECRET-TEXT" not in str(info.value)


def test_dataset_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "d.jsonl"
    path.write_text(json.dumps(case_dict("a")) + "\n\n", encoding="utf-8")
    assert [c.id for c in load_cases(path)] == ["a"]
