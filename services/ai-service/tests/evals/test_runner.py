from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from ai_service.llm.types import LlmRequest, ProviderError
from evals.grade.runner import (
    DEFAULT_MAX_COST_USD,
    DEFAULT_RUNS,
    EvalResult,
    RunResult,
    compute_metrics,
    grade_case,
    render_report,
    resolve_model,
    run_eval,
)
from evals.grade.schema import EvalCase
from tests.evals.helpers import ScriptedAdapter, case_dict, case_with, output

PRODUCTION_MODEL = "claude-haiku-5-5"


def cases(*dicts: dict[str, Any]) -> list[EvalCase]:
    return [EvalCase.model_validate(d) for d in dicts]


def verdict_run(overall: str, units: list[str] | None = None) -> RunResult:
    return RunResult(
        kind="verdict",
        overall=overall,  # pyright: ignore[reportArgumentType]
        units=tuple(units or [overall]),  # pyright: ignore[reportArgumentType]
        cost=Decimal(0),
        latency_ms=1,
    )


def error_run(kind: str) -> RunResult:
    return RunResult(kind=kind, overall=None, units=(), cost=Decimal(0), latency_ms=1)  # pyright: ignore[reportArgumentType]


def result_of(runs: dict[str, list[RunResult]], n: int = 3, *, early: bool = False) -> EvalResult:
    return EvalResult(
        runs=n,
        results=runs,
        spent=Decimal(0),
        stopped_early=early,
        provider="fake",
        model="m",
        model_overridden=False,
        prompt_version="v1",
        prompt_sha256="x",
    )


def by_unit_text(request: LlmRequest) -> str:
    return request.user


def echo_expected(case_dict_list: list[dict[str, Any]]):
    """An adapter that returns each case's expected units, found by its answer text."""
    table = {d["answer"]: d["expected"]["units"] for d in case_dict_list}

    def script(_n: int, request: LlmRequest) -> str:
        for answer, units in table.items():
            if answer in request.user:
                return output(list(units))
        raise AssertionError("unknown case")

    return script


# --- defaults and model (O1) ---------------------------------------------------------------


def test_runs_default_three() -> None:
    assert DEFAULT_RUNS == 3
    assert DEFAULT_MAX_COST_USD == Decimal("1.00")


def test_model_defaults_to_production_grade_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_LLM_MODELS", raising=False)
    adapter = ScriptedAdapter(lambda n, r: "", fixed_model=None)
    assert resolve_model(adapter, None) == (PRODUCTION_MODEL, False)
    assert resolve_model(adapter, PRODUCTION_MODEL) == (PRODUCTION_MODEL, False)
    assert resolve_model(adapter, "other") == ("other", True)


def test_production_model_follows_ai_llm_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_LLM_MODELS", '{"grade": "claude-x"}')
    adapter = ScriptedAdapter(lambda n, r: "", fixed_model=None)
    assert resolve_model(adapter, None) == ("claude-x", False)


def test_fixed_model_of_the_adapter_wins_by_default() -> None:
    adapter = ScriptedAdapter(lambda n, r: "", fixed_model="fake-grader-v1")
    assert resolve_model(adapter, None) == ("fake-grader-v1", False)


def test_unpriced_model_refused_before_any_call() -> None:
    adapter = ScriptedAdapter(lambda n, r: output(["correct"]), fixed_model=None)
    with pytest.raises(LookupError):
        run_eval(cases(case_dict()), adapter, model="no-such-model")
    assert adapter.calls == []


# --- one call ------------------------------------------------------------------------------


def test_grade_case_uses_production_prompt_and_retries_once_with_same_nonce() -> None:
    def script(n: int, request: LlmRequest) -> str:
        return "not json" if n == 1 else output(["correct"])

    adapter = ScriptedAdapter(script)
    run = grade_case(cases(case_dict())[0], adapter, model="fake-grader-v1")
    assert run.kind == "verdict" and run.overall == "correct"
    first, second = adapter.calls
    assert (first.attempt, second.attempt) == (1, 2)
    assert first.system == second.system and first.user == second.user  # same nonce
    assert first.prompt_version == "v1"


def test_repeated_output_violation_is_not_stable() -> None:
    adapter = ScriptedAdapter(lambda n, r: "not json")
    result = run_eval(cases(case_dict()), adapter, model="fake-grader-v1", runs=2)
    assert [r.kind for r in result.results["c1"]] == ["output_invalid"] * 2
    assert len(adapter.calls) == 4  # two tries each
    metrics = compute_metrics(cases(case_dict()), result)
    assert metrics.stability == 0.0
    assert metrics.overall_match == 0.0
    assert metrics.errors == {"output_invalid": 2, "provider_error": 0}


def test_provider_error_counts_as_miss_and_unstable() -> None:
    def script(n: int, request: LlmRequest) -> str | ProviderError:
        return ProviderError("rate_limited") if n == 2 else output(["correct"])

    data = [case_dict()]
    adapter = ScriptedAdapter(script)
    result = run_eval(cases(*data), adapter, model="fake-grader-v1", runs=3)  # must not raise
    assert [r.kind for r in result.results["c1"]] == ["verdict", "provider_error", "verdict"]
    metrics = compute_metrics(cases(*data), result)
    assert metrics.stability == 0.0
    assert metrics.errors["provider_error"] == 1


# --- metrics (AC4, AC5, AC6, AC7, AC9, AC10) -----------------------------------------------


def test_overall_match_rate_counts_errors_in_the_denominator() -> None:
    cs = cases(case_with("a", "correct"), case_with("b", "correct"), case_with("c", "partial"))
    result = result_of(
        {
            "a": [verdict_run("correct")] * 3,
            "b": [verdict_run("partial")] * 3,
            "c": [error_run("provider_error")] * 3,
        }
    )
    metrics = compute_metrics(cs, result)
    assert metrics.overall_match == pytest.approx(1 / 3)
    assert metrics.unit_match == pytest.approx(1 / 3)


def test_false_correct_rate_denominator_is_incorrect_cases() -> None:
    cs = cases(
        case_with("a", "incorrect"),
        case_with("b", "incorrect"),
        case_with("c", "correct"),
        case_with("d", "correct"),
    )
    result = result_of(
        {
            "a": [verdict_run("correct")] * 3,  # the bad one
            "b": [verdict_run("incorrect")] * 3,
            "c": [verdict_run("correct")] * 3,
            "d": [verdict_run("correct")] * 3,
        }
    )
    assert compute_metrics(cs, result).false_correct == 0.5


def test_false_correct_is_none_without_incorrect_cases() -> None:
    cs = cases(case_with("a", "correct"))
    metrics = compute_metrics(cs, result_of({"a": [verdict_run("correct")] * 3}))
    assert metrics.false_correct is None
    assert "n/a" in render_report(metrics, result_of({"a": [verdict_run("correct")] * 3}))


def test_per_unit_match_rate_multi_unit() -> None:
    two = case_dict(
        "m",
        units=[
            {"title": "A", "sources": ["aaa"]},
            {"title": "B", "sources": ["bbb"]},
        ],
        expected={"overall": "partial", "units": ["correct", "incorrect"]},
    )
    cs = cases(two)
    result = result_of({"m": [verdict_run("partial", ["correct", "correct"])] * 3})
    metrics = compute_metrics(cs, result)
    assert metrics.overall_match == 1.0  # overall matches ...
    assert metrics.unit_match == 0.5  # ... but one unit of two is wrong


def test_stability_counts_only_identical_across_all_runs() -> None:
    cs = cases(case_with("a", "correct"), case_with("b", "correct"))
    result = result_of(
        {
            "a": [verdict_run("correct")] * 3,
            "b": [verdict_run("correct"), verdict_run("partial"), verdict_run("correct")],
        }
    )
    assert compute_metrics(cs, result).stability == 0.5


def test_stability_ignores_cases_without_all_runs() -> None:
    cs = cases(case_with("a", "correct"), case_with("b", "correct"))
    result = result_of(
        {"a": [verdict_run("correct")] * 3, "b": [verdict_run("correct")]}, early=True
    )
    metrics = compute_metrics(cs, result)
    assert metrics.stability == 1.0
    assert metrics.complete is False


def test_category_breakdown_flags_failed_paraphrase() -> None:
    cs = cases(
        case_with("p", "correct", category="paraphrase"),
        case_with("t", "correct", category="typo"),
        case_with("i", "incorrect", category="injection"),
    )
    result = result_of(
        {
            "p": [verdict_run("partial")] * 3,
            "t": [verdict_run("correct")] * 3,
            "i": [verdict_run("correct")] * 3,
        }
    )
    metrics = compute_metrics(cs, result)
    assert metrics.right_idea_failed == ["p"]
    assert metrics.by_category["injection"] == (0, 1)
    assert metrics.by_category["typo"] == (1, 1)


def test_level_counts_warn_below_15() -> None:
    cs = cases(case_with("a", "correct", level=1), case_with("b", "correct", level=2))
    result = result_of({"a": [verdict_run("correct")] * 3, "b": [verdict_run("correct")] * 3})
    metrics = compute_metrics(cs, result)
    assert metrics.level_counts == {1: 1, 2: 1, 3: 0}
    report = render_report(metrics, result)
    assert "fewer than 15" in report


# --- running -------------------------------------------------------------------------------


def test_run_eval_runs_every_case_every_time() -> None:
    data = [case_with("a", "correct"), case_with("b", "partial")]
    data[1]["answer"] = "different answer"
    adapter = ScriptedAdapter(echo_expected(data))
    result = run_eval(cases(*data), adapter, model="fake-grader-v1", runs=3)
    assert len(adapter.calls) == 6
    assert all(len(v) == 3 for v in result.results.values())
    metrics = compute_metrics(cases(*data), result)
    assert metrics.overall_match == 1.0 and metrics.stability == 1.0


def test_cost_ceiling_stops_before_next_call() -> None:
    data = [case_with(f"c{i}", "correct") for i in range(3)]
    adapter = ScriptedAdapter(
        lambda n, r: output(["correct"]), tokens=(1000, 500), fixed_model=None
    )
    ceiling = Decimal("0.001")
    result = run_eval(cases(*data), adapter, model=PRODUCTION_MODEL, runs=3, max_cost_usd=ceiling)
    assert result.stopped_early
    assert 0 < len(adapter.calls) < 9
    assert result.spent <= ceiling


def test_retry_cost_counts_toward_the_ceiling() -> None:
    def script(n: int, request: LlmRequest) -> str:
        return "not json" if n == 1 else output(["correct"])

    adapter = ScriptedAdapter(script, tokens=(1000, 500), fixed_model=None)
    result = run_eval(cases(case_dict()), adapter, model=PRODUCTION_MODEL, runs=1)
    assert result.spent == Decimal("0.0007")  # two calls of 0.00035


@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf"])
def test_ceiling_must_be_a_positive_finite_number(bad: str) -> None:
    from evals.grade.runner import parse_ceiling

    with pytest.raises(ValueError):
        parse_ceiling(bad)


def test_report_marks_incomplete_and_prints_no_pass() -> None:
    cs = cases(case_with("a", "correct"))
    result = result_of({"a": [verdict_run("correct")]}, early=True)
    report = render_report(compute_metrics(cs, result), result)
    assert "stopped early" in report
    assert "PASS" not in report


def test_markdown_report_has_metrics_and_no_answers() -> None:
    data = [
        case_dict(
            "a",
            answer="SECRET ANSWER TEXT",
            question={"text": "SECRET Q", "reference_answer": "SECRET REF"},
        )
    ]
    cs = cases(*data)
    adapter = ScriptedAdapter(lambda n, r: output(["correct"]))
    result = run_eval(cs, adapter, model="fake-grader-v1", runs=3)
    report = render_report(compute_metrics(cs, result), result)
    assert "SECRET" not in report
    assert "provider: fake" in report and "prompt: v1" in report
    for word in ("Label match", "Stability", "PASS"):
        assert word in report


def test_report_says_when_the_model_is_not_the_production_one() -> None:
    cs = cases(case_dict())
    adapter = ScriptedAdapter(lambda n, r: output(["correct"]))
    result = run_eval(cs, adapter, model="fake-grader-v1", runs=1)
    result = replace(result, model_overridden=True)
    assert "differs from production" in render_report(compute_metrics(cs, result), result)


def test_threshold_boundaries() -> None:
    from evals.grade.runner import status

    assert status(0.85, 0.85, higher_is_better=True, complete=True) == "PASS"
    assert status(0.84, 0.85, higher_is_better=True, complete=True) == "FAIL"
    assert status(0.05, 0.05, higher_is_better=False, complete=True) == "PASS"
    assert status(0.06, 0.05, higher_is_better=False, complete=True) == "FAIL"
    assert status(None, 0.85, higher_is_better=True, complete=True) == "n/a"
    assert status(1.0, 0.85, higher_is_better=True, complete=False) == "n/a"


def test_any_exception_in_one_case_is_a_provider_error_and_the_run_continues() -> None:
    # R55 (T3.2): a bug or an odd error from the SDK in one case must not end the whole run.
    def script(n: int, request: LlmRequest) -> str | ProviderError:
        if n == 1:
            raise RuntimeError("boom")
        return output(["correct"])

    data = [case_dict("c1"), case_dict("c2")]
    adapter = ScriptedAdapter(script)
    result = run_eval(cases(*data), adapter, model="fake-grader-v1", runs=1)  # must not raise
    assert [r.kind for r in result.results["c1"]] == ["provider_error"]
    assert [r.kind for r in result.results["c2"]] == ["verdict"]
