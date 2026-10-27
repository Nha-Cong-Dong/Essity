"""Edge cases of the grade eval runner found by the independent tester (T3.1)."""

from decimal import Decimal
from typing import Any

import pytest

from ai_service.llm.pricing import price_for
from ai_service.tasks.grade import build_llm_request
from evals.grade import runner
from evals.grade.runner import (
    EvalResult,
    RunResult,
    compute_metrics,
    render_report,
    run_eval,
)
from evals.grade.schema import EvalCase
from tests.evals.helpers import ScriptedAdapter, case_dict, case_with, output

PRODUCTION_MODEL = "claude-haiku-5-5"


def cases(*dicts: dict[str, Any]) -> list[EvalCase]:
    return [EvalCase.model_validate(d) for d in dicts]


def run_of(overall: str) -> RunResult:
    return RunResult(
        kind="verdict",
        overall=overall,  # pyright: ignore[reportArgumentType]
        units=(overall,),  # pyright: ignore[reportArgumentType]
        cost=Decimal(0),
        latency_ms=1,
    )


def result_of(runs: dict[str, list[RunResult]], n: int = 3) -> EvalResult:
    return EvalResult(
        runs=n,
        results=runs,
        spent=Decimal(0),
        stopped_early=False,
        provider="fake",
        model="m",
        model_overridden=False,
        prompt_version="v1",
        prompt_sha256="x",
    )


def row_status(report: str, metric: str) -> str:
    row = next(line for line in report.splitlines() if line.startswith(f"| {metric}"))
    return row.rstrip(" |").rsplit("|", 1)[-1].strip()


def worst_prompt_chars(case: EvalCase) -> int:
    llm = build_llm_request(runner._request(case), run_id=runner._id(case, "r"), attempt=1)  # pyright: ignore[reportPrivateUsage]
    return len(llm.system) + len(llm.user)


# Red when: label match is taken from a later run (a lucky retry) instead of the first one.
def test_label_match_uses_the_first_run_not_a_later_one() -> None:
    cs = cases(case_with("a", "correct"))
    metrics = compute_metrics(cs, result_of({"a": [run_of("partial"), run_of("correct")]}, 2))
    assert metrics.overall_match == 0.0
    assert metrics.unit_match == 0.0


# Red when: stability looks at only some of the runs (here the last one is the odd one out).
def test_stability_breaks_when_only_the_last_run_differs() -> None:
    cs = cases(case_with("a", "correct"))
    runs = [run_of("correct"), run_of("correct"), run_of("incorrect")]
    assert compute_metrics(cs, result_of({"a": runs})).stability == 0.0


# Red when: a partial grade on a case labelled incorrect counts as "graded correct" (AC4).
def test_partial_on_an_incorrect_case_is_not_false_correct() -> None:
    cs = cases(case_with("a", "incorrect"), case_with("b", "incorrect"))
    result = result_of({"a": [run_of("partial")] * 3, "b": [run_of("correct")] * 3})
    assert compute_metrics(cs, result).false_correct == 0.5


# Red when: a threshold drifts from US-05 (AC4 85% / 5%, AC6 95%).
@pytest.mark.parametrize(
    ("metric", "good", "bad"),
    [
        ("Label match, overall (AC4)", 17, 16),  # 85% PASS, 80% FAIL
        ("Incorrect graded correct (AC4)", 1, 2),  # 5% PASS, 10% FAIL
        ("Stability over 3 runs (AC6)", 19, 18),  # 95% PASS, 90% FAIL
    ],
)
def test_thresholds_are_the_us05_values(metric: str, good: int, bad: int) -> None:
    ids = [f"c{i}" for i in range(20)]
    label = "incorrect" if "Incorrect" in metric else "correct"
    cs = cases(*(case_with(i, label) for i in ids))

    def report_with(k: int) -> str:
        runs: dict[str, list[RunResult]] = {}
        for n, i in enumerate(ids):
            if metric.startswith("Label"):
                runs[i] = [run_of("correct" if n < k else "partial")] * 3
            elif metric.startswith("Incorrect"):
                runs[i] = [run_of("correct" if n < k else "incorrect")] * 3
            else:
                stable = [run_of("correct")] * 3
                runs[i] = (
                    stable if n < k else [run_of("correct"), run_of("partial"), run_of("correct")]
                )
        result = result_of(runs)
        return render_report(compute_metrics(cs, result), result)

    assert row_status(report_with(good), metric) == "PASS"
    assert row_status(report_with(bad), metric) == "FAIL"


# Red when: the worst case of a call leaves out the prompt, so a long prompt can pass the ceiling.
def test_ceiling_counts_the_prompt_not_only_the_output() -> None:
    cs = cases(case_dict())
    adapter = ScriptedAdapter(lambda n, r: output(["correct"]), fixed_model=None)
    adapter.params = {"max_tokens": 1}
    ceiling = Decimal("0.0001")  # the prompt alone is worth more than this
    assert worst_prompt_chars(cs[0]) * Decimal("0.10") / 1_000_000 > ceiling
    result = run_eval(cs, adapter, model=PRODUCTION_MODEL, runs=1, max_cost_usd=ceiling)
    assert adapter.calls == []
    assert result.stopped_early


# Red when: the runner goes case by case, so an early stop leaves some cases with no run at all.
def test_early_stop_leaves_whole_runs() -> None:
    data = [case_with(f"c{i}", "correct") for i in range(3)]
    for i, d in enumerate(data):
        d["answer"] = f"answer number {i}"
    cs = cases(*data)
    price = price_for(PRODUCTION_MODEL)
    worst = max(worst_prompt_chars(c) for c in cs) * price.input_per_mtok / 1_000_000
    worst += 800 * price.output_per_mtok / 1_000_000
    assert worst < Decimal("0.001")  # each call costs 0.001, so the ceiling lets 4 calls through
    adapter = ScriptedAdapter(
        lambda n, r: output(["correct"]), tokens=(10_000, 0), fixed_model=None
    )
    result = run_eval(cs, adapter, model=PRODUCTION_MODEL, runs=3, max_cost_usd=Decimal("0.004"))
    assert result.stopped_early
    assert len(adapter.calls) == 4
    assert sorted(len(v) for v in result.results.values()) == [1, 1, 2]


# Red when: a try past the deadline still calls the model (with a negative timeout).
def test_no_call_after_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "DEADLINE_SECONDS", 0.0)
    adapter = ScriptedAdapter(lambda n, r: output(["correct"]))
    run = runner.grade_case(cases(case_dict())[0], adapter, model="fake-grader-v1")
    assert run.kind == "provider_error"
    assert adapter.calls == []


# Red when: a blank answer reaches the model in the eval, though production grades it incorrect
# without any call (grade.py `if not request.answer.strip()`): the eval would measure another path.
def test_blank_answer_case_is_refused() -> None:
    with pytest.raises(ValueError):
        EvalCase.model_validate(case_dict(answer="   "))


# Red when: the report does not say which cases missed (plan: "ca sai: id, kỳ vọng, nhận được").
def test_report_lists_missed_case_ids() -> None:
    cs = cases(case_with("ok-1", "correct"), case_with("miss-1", "correct"))
    result = result_of({"ok-1": [run_of("correct")] * 3, "miss-1": [run_of("partial")] * 3})
    report = render_report(compute_metrics(cs, result), result)
    assert "miss-1" in report
    assert "ok-1" not in report
