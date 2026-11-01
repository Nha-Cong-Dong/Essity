"""T8.4b: the practice-grading eval dataset and its command line (US-05 AC10). CI uses fakes only:
the 85% / 5% thresholds are asserted by the manual run against the real model (see the runner)."""

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from ai_service.llm.types import AdapterResult, LlmRequest
from evals.grade_practice import runner
from evals.grade_practice.runner import CASES_MIN, DEFAULT_CASES, load_cases, main, oracle_ask, run


def _refuse(*args: Any, **kwargs: Any) -> None:
    raise AssertionError("real model built")


def test_dataset_has_40_cases_with_mix_and_unique_answers() -> None:
    # Red when: fewer than 40 cases, a category or label missing, fewer than 10 really-wrong
    # answers (the denominator of the false "Đúng" rate), or a repeated answer (the oracle finds
    # a case by its answer).
    cases = load_cases(DEFAULT_CASES)
    assert len(cases) >= CASES_MIN == 40
    by_category = Counter(c.category for c in cases)
    assert set(by_category) == {"bank_answer", "ai_answer", "injection"}
    assert min(by_category.values()) >= 12
    labels = {label for c in cases for label in c.expected}
    assert labels == {"yes", "partial", "no"}
    assert sum(set(c.expected) == {"no"} for c in cases) >= 10
    assert len({c.answer for c in cases}) == len(cases)


def test_oracle_matches_every_label_so_the_harness_and_labels_agree() -> None:
    # Red when: a case's answer shows up in an earlier case's prompt (the oracle would answer the
    # wrong case), or a label does not fit its rubric.
    cases = load_cases(DEFAULT_CASES)
    report = run(cases, oracle_ask(cases))
    assert report.match_rate == 1.0 and report.false_correct == 0 and report.passed


def test_main_fake_provider_makes_no_network_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Red when: the default run builds the real client or needs a key.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    monkeypatch.setattr(runner, "anthropic_ask", _refuse)
    lines: list[str] = []
    assert main([], out=lines.append) == 0
    assert "PASS" in lines[-1]
    assert capsys.readouterr().err == ""


def test_anthropic_without_key_exits_before_any_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Red when: the real provider starts with no key, or builds a client first.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(runner, "anthropic_ask", _refuse)
    assert main(["--provider", "anthropic"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


@pytest.mark.parametrize("ceiling", ["0", "-1", "abc", "nan"])
def test_bad_ceiling_is_refused(ceiling: str) -> None:
    assert main(["--max-cost-usd", ceiling]) == 2


class _Adapter:
    calls = 0

    def __init__(self, api_key: str) -> None:
        assert api_key == "sk-test"

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        type(self).calls += 1
        return AdapterResult(text="{}", input_tokens=10, output_tokens=5, stop_reason="end_turn")


def test_ceiling_stops_the_run_before_the_call_that_could_pass_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: the cost ceiling is only checked after a call (budget spent past the limit).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr("ai_service.llm.anthropic_adapter.AnthropicAdapter", _Adapter)
    _Adapter.calls = 0
    assert main(["--provider", "anthropic", "--max-cost-usd", "0.000001"]) == 2
    assert _Adapter.calls == 0


def test_malformed_dataset_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json\n", "utf-8")
    assert main(["--cases", str(bad)]) == 2
