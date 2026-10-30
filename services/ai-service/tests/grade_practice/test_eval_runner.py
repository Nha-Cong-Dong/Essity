"""T8.4a: the grade_practice eval scaffold works with a fake model (US-05 AC10)."""

import json
from pathlib import Path

import pytest

from ai_service.tasks.grade_practice import PracticePrompt
from evals.grade_practice.runner import load_cases, run

CASES = Path(__file__).resolve().parents[2] / "evals" / "grade_practice" / "cases.jsonl"


def _oracle(prompt: PracticePrompt) -> str:
    """Answers each case as labelled (looked up by the learner answer in the prompt)."""
    for case in load_cases(CASES):
        if case.answer in prompt.user:
            ideas = [
                {"idea": f"R{n}", "verdict": v, "anchor": case.answer if v != "no" else None}
                for n, v in enumerate(case.expected, start=1)
            ]
            return json.dumps({"ideas": ideas})
    raise AssertionError("unknown case")


def test_sample_cases_load_and_cover_both_answer_origins() -> None:
    cases = load_cases(CASES)
    assert {c.category for c in cases} >= {"bank_answer", "ai_answer", "injection"}


def test_perfect_model_passes() -> None:
    report = run(load_cases(CASES), _oracle)
    assert report.match_rate == 1.0 and report.false_correct == 0 and report.passed


def test_model_that_always_says_yes_fails_on_false_correct() -> None:
    def always_yes(prompt: PracticePrompt) -> str:
        n = prompt.user.count('kind="idea"')
        ideas = [{"idea": f"R{i}", "verdict": "yes", "anchor": None} for i in range(1, n + 1)]
        return json.dumps({"ideas": ideas})

    report = run(load_cases(CASES), always_yes)
    assert report.false_correct >= 1 and not report.passed


def test_ungraded_case_counts_as_miss() -> None:
    report = run(load_cases(CASES), lambda _p: "not json")
    assert len(report.not_graded) == report.cases and not report.passed


def test_mislabelled_case_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    case = {
        "id": "x",
        "category": "bank_answer",
        "question": "q",
        "rubric": ["a", "b"],
        "reference_answer": "r",
        "answer": "a",
        "expected": ["yes"],
    }
    bad.write_text(json.dumps(case), "utf-8")
    with pytest.raises(ValueError):
        load_cases(bad)
