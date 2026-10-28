"""The extract eval harness (T4.11, US-02 AC6): schema checks, matching, runner, report."""

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ai_service.llm.types import LlmRequest, ProviderError
from evals.extract.runner import (
    DEFAULT_CASES,
    compute_metrics,
    main,
    render_report,
    run_eval,
)
from evals.extract.schema import ExtractCase, build_request, load_cases
from tests.evals.helpers import ScriptedAdapter


def case_dict(case_id: str = "c1", **overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "id": case_id,
        "category": "section",
        "description": "hôm qua học chương 3 giáo trình",
        "docs": [{"book": "giaotrinh"}],
        "expected": {
            "status": "proposed",
            "days_ago": 1,
            "ranges": [{"doc": 0, "start": 51, "end": 74}],
        },
    }
    case.update(overrides)
    return case


def make(case_id: str = "c1", **overrides: Any) -> ExtractCase:
    return ExtractCase.model_validate(case_dict(case_id, **overrides))


def proposed_text(section: str = "D1.S5", *, days_ago: int | None = 1) -> str:
    return json.dumps(
        {
            "status": "proposed",
            "studied_day": {"days_ago": days_ago, "date": None},
            "ranges": [
                {
                    "doc": "D1",
                    "kind": "section",
                    "from_section": section,
                    "to_section": None,
                    "basis": None,
                    "from_page": None,
                    "to_page": None,
                    "depth": "deep",
                }
            ],
            "question": None,
            "reason": None,
            "candidates": [],
        }
    )


# --- the dataset ----------------------------------------------------------------------------


def test_shipped_dataset_is_valid_and_wide_enough() -> None:
    cases = load_cases(DEFAULT_CASES)
    assert len(cases) >= 30
    assert {c.category for c in cases} >= {
        "section", "pages_printed", "pages_file", "continue", "multi_range",
        "mixed_lang", "typo", "note_only", "clarify",
    }  # fmt: skip
    assert {c.expected.status for c in cases} == {"proposed", "note_only", "clarify"}
    assert any(len(c.docs) > 1 for c in cases)


def test_every_case_builds_a_request_the_service_accepts() -> None:
    for case in load_cases(DEFAULT_CASES):
        build_request(case)


def test_case_with_pages_beyond_its_book_is_refused() -> None:
    bad = case_dict(expected={"status": "proposed", "ranges": [{"doc": 0, "start": 70, "end": 99}]})
    with pytest.raises(ValueError, match="beyond"):
        ExtractCase.model_validate(bad)


def test_case_with_unknown_doc_index_or_book_is_refused() -> None:
    with pytest.raises(ValueError):
        make(expected={"status": "proposed", "ranges": [{"doc": 3, "start": 1, "end": 2}]})
    with pytest.raises(ValueError):
        make(docs=[{"book": "nope"}])


def test_label_must_fit_status() -> None:
    with pytest.raises(ValueError):
        make(expected={"status": "clarify"})  # no reason
    with pytest.raises(ValueError):
        make(expected={"status": "note_only", "ranges": [{"doc": 0, "start": 1, "end": 2}]})
    with pytest.raises(ValueError):
        make(expected={"status": "proposed", "ranges": []})


def test_duplicate_ids_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(case_dict("a")) for _ in range(2)), "utf-8")
    with pytest.raises(ValueError, match="duplicate id"):
        load_cases(path)


# --- one run --------------------------------------------------------------------------------


Script = Callable[[int, LlmRequest], str | ProviderError]


def run(case: ExtractCase, script: Script, **kwargs: Any):
    adapter = ScriptedAdapter(
        script, fixed_model="fake-grader-v1", tokens=kwargs.pop("tokens", (0, 0))
    )
    return adapter, run_eval([case], adapter, model="fake-grader-v1", **kwargs)


def test_matching_output_is_a_hit() -> None:
    _, result = run(make(), lambda n, r: proposed_text())
    metrics = compute_metrics([make()], result)
    assert metrics.accuracy == 1.0 and metrics.complete


def test_wrong_pages_wrong_day_or_wrong_depth_is_a_miss() -> None:
    for text in (proposed_text("D1.S1"), proposed_text(days_ago=0), proposed_text(days_ago=None)):
        _, result = run(make(), lambda n, r, t=text: t)
        assert compute_metrics([make()], result).accuracy == 0.0


def test_broken_output_is_retried_once_then_counted_invalid() -> None:
    adapter, result = run(make(), lambda n, r: "not json")
    assert len(adapter.calls) == 2
    metrics = compute_metrics([make()], result)
    assert metrics.accuracy == 0.0 and metrics.errors == {"output_invalid": 1, "provider_error": 0}


def test_second_try_after_broken_output_can_match() -> None:
    adapter, result = run(make(), lambda n, r: "oops" if n == 1 else proposed_text())
    assert len(adapter.calls) == 2
    assert compute_metrics([make()], result).accuracy == 1.0


def test_provider_error_keeps_the_denominator() -> None:
    cases = [make("a"), make("b")]
    adapter = ScriptedAdapter(
        lambda n, r: proposed_text() if n == 1 else ProviderError("boom"),
        fixed_model="fake-grader-v1",
    )
    result = run_eval(cases, adapter, model="fake-grader-v1")
    metrics = compute_metrics(cases, result)
    assert metrics.accuracy == 0.5
    assert metrics.errors["provider_error"] == 1


def test_clarify_is_matched_on_status_and_reason() -> None:
    clarify = make(
        "k", category="clarify", expected={"status": "clarify", "reason": "ambiguous_range"}
    )
    out = json.dumps(
        {
            "status": "clarify",
            "studied_day": {"days_ago": None, "date": None},
            "ranges": [],
            "question": "Bạn học trang nào?",
            "reason": "ambiguous_range",
            "candidates": [],
        }
    )
    _, result = run(clarify, lambda n, r: out)
    assert compute_metrics([clarify], result).accuracy == 1.0
    _, wrong = run(clarify, lambda n, r: out.replace("ambiguous_range", "missing_info"))
    assert compute_metrics([clarify], wrong).accuracy == 0.0


def test_cost_ceiling_stops_the_run_without_a_verdict() -> None:
    cases = [make("a"), make("b")]
    adapter = ScriptedAdapter(
        lambda n, r: proposed_text(), fixed_model="claude-haiku-5-5", tokens=(1000, 100)
    )
    result = run_eval(cases, adapter, model="claude-haiku-5-5", max_cost_usd=Decimal("0.0001"))
    assert result.stopped_early and not adapter.calls
    metrics = compute_metrics(cases, result)
    assert not metrics.complete
    assert "no verdict" in render_report(metrics, result)


def test_unpriced_model_is_refused_before_any_call() -> None:
    adapter = ScriptedAdapter(lambda n, r: proposed_text())
    with pytest.raises(LookupError):
        run_eval([make()], adapter, model="not-a-model")
    assert not adapter.calls


# --- report and command line ----------------------------------------------------------------


def test_report_has_numbers_and_ids_only() -> None:
    _, result = run(make(), lambda n, r: proposed_text("D1.S1"))
    text = render_report(compute_metrics([make()], result), result)
    assert "| Accuracy (US-02 AC6) | 0.0% | >= 90% | FAIL |" in text
    assert "c1" in text
    assert "hôm qua" not in text and "giáo trình" not in text


def test_cli_runs_shipped_cases_with_the_fake_provider(tmp_path: Path) -> None:
    report = tmp_path / "out" / "report.md"
    assert main(["--out", str(report)]) == 0
    text = report.read_text("utf-8")
    assert "provider: fake" in text
    assert "harness only" in text
    assert "## By category" in text


def test_cli_refuses_the_real_provider_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        main(["--provider", "anthropic"])
