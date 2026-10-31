"""The shared eval runner (T9.7a): ceiling, per-case errors, report, thresholds, CLI."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ai_service.llm.pricing import Price
from evals.draft_units.suite import SUITE as DRAFT
from evals.framework import cli
from evals.framework.gateway import ScriptedGateway
from evals.framework.runner import (
    CeilingReachedError,
    CostGuard,
    EvalCase,
    GuardedAsk,
    Scored,
    Suite,
    compute_metrics,
    load_cases,
    parse_ceiling,
    render_report,
    run_suite,
)

PRICED = Price(input_per_mtok=Decimal(1_000_000), output_per_mtok=Decimal(1_000_000))  # $1/token


class Prompt:
    system = "s"
    user = "u"
    output_schema: dict[str, Any] = {}


def make_suite(score: Any, thresholds: dict[str, float | None] | None = None) -> Suite[EvalCase]:
    return Suite(
        name="toy",
        case_model=EvalCase,
        task="draft_units",
        score=score,
        thresholds=thresholds if thresholds is not None else {"acc": None},
    )


def cases(*ids: str) -> list[EvalCase]:
    return [EvalCase(id=i) for i in ids]


def gateway(*replies: str | Exception) -> ScriptedGateway:
    return ScriptedGateway(list(replies) or ["x"])


def priced_gateway(max_tokens: int) -> ScriptedGateway:
    g = ScriptedGateway(["x"], price=PRICED, tokens=(1, 1))
    g.max_tokens = max_tokens
    return g


def test_per_case_exception_is_captured_and_run_goes_on() -> None:
    def score(case: EvalCase, ask: GuardedAsk) -> Scored:
        if case.id == "bad":
            raise RuntimeError("secret learner text")
        return Scored(True, {"acc": (1, 1)})

    suite = make_suite(score)
    result = run_suite(suite, cases("a", "bad", "c"), lambda c: gateway())
    assert result.outcomes["bad"].error == "RuntimeError"
    assert result.outcomes["c"].scored is not None
    report = render_report(suite, result)
    assert "secret learner text" not in report
    assert "Errors (counted as a miss): 1." in report
    assert "- bad" in report
    assert compute_metrics(result).hit_rate == pytest.approx(2 / 3)


def test_provider_exception_inside_ask_is_that_cases_error() -> None:
    def score(case: EvalCase, ask: GuardedAsk) -> Scored:
        ask(Prompt())
        return Scored(True)

    result = run_suite(make_suite(score), cases("a"), lambda c: gateway(TimeoutError()))
    assert result.outcomes["a"].error == "TimeoutError"


def test_cost_ceiling_stops_before_the_call_that_would_pass_it() -> None:
    calls: list[str] = []

    def score(case: EvalCase, ask: GuardedAsk) -> Scored:
        calls.append(case.id)
        ask(Prompt())
        return Scored(True, {"acc": (1, 1)})

    suite = make_suite(score)
    # A call books 2 (1 in + 1 out token at $1); its worst case is 2 input chars + 5 out = 7.
    result = run_suite(
        suite, cases("a", "b", "c", "d"), lambda c: priced_gateway(5), max_cost_usd=Decimal(12)
    )
    assert result.stopped_early
    assert list(result.outcomes) == ["a", "b"]
    assert calls == ["a", "b", "c"]  # c started, its call was refused
    assert result.spent == Decimal(4)
    report = render_report(suite, result)
    assert "stopped early" in report
    assert "| acc | 100.0% | unset" in report
    assert "PASS" not in report and "FAIL" not in report


def test_a_task_that_swallows_the_ceiling_signal_still_stops_the_run() -> None:
    def score(case: EvalCase, ask: GuardedAsk) -> Scored:
        try:
            ask(Prompt())
        except CeilingReachedError:
            pass
        return Scored(True)

    result = run_suite(
        make_suite(score), cases("a", "b"), lambda c: priced_gateway(100), max_cost_usd=Decimal(10)
    )
    assert result.stopped_early
    assert result.outcomes == {}


def test_guard_allows_exactly_the_ceiling() -> None:
    guard = CostGuard(Decimal(5))
    guard.check(Decimal(5))
    with pytest.raises(CeilingReachedError):
        guard.check(Decimal("5.000001"))


def test_threshold_unset_gives_na_and_set_gives_verdict() -> None:
    def score(case: EvalCase, ask: GuardedAsk) -> Scored:
        return Scored(case.id == "a", {"acc": (int(case.id == "a"), 1)})

    unset = make_suite(score)
    result = run_suite(unset, cases("a", "b"), lambda c: gateway())
    assert "| acc | 50.0% | unset (to be set when the first data exists) | n/a |" in render_report(
        unset, result
    )
    strict = make_suite(score, {"acc": 0.9})
    assert "| acc | 50.0% | >= 90% | FAIL |" in render_report(strict, result)
    lax = make_suite(score, {"acc": 0.4})
    assert "| acc | 50.0% | >= 40% | PASS |" in render_report(lax, result)


def test_fake_provider_report_says_it_measures_the_harness() -> None:
    suite = make_suite(lambda c, a: Scored(True))  # pyright: ignore[reportUnknownLambdaType]
    report = render_report(suite, run_suite(suite, cases("a"), lambda c: gateway()))
    assert "checks the harness only" in report


def test_load_cases_rejects_bad_lines_without_echoing_them(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    path.write_text('{"id": "a", "oops": "learner words"}\n', "utf-8")
    with pytest.raises(ValueError, match="line 1") as info:
        load_cases(DRAFT, path)
    assert "learner words" not in str(info.value)
    path.write_text("not json\n", "utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_cases(DRAFT, path)
    row = '{"id": "a", "notes": "x", "expected": []}\n'
    path.write_text(row + row, "utf-8")
    with pytest.raises(ValueError, match="duplicate id a"):
        load_cases(DRAFT, path)


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "nan", "inf"])
def test_parse_ceiling_refuses_nonsense(bad: str) -> None:
    with pytest.raises(ValueError, match="cost ceiling"):
        parse_ceiling(bad)


@pytest.mark.parametrize("name", sorted(cli.SUITES))
def test_cli_runs_every_suite_on_its_sample_with_fake_replies(name: str, tmp_path: Path) -> None:
    target = tmp_path / "docs" / "evals" / f"{name}.md"
    lines: list[str] = []
    assert cli.main(["--suite", name, "--out", str(target)], out=lines.append) == 0
    report = target.read_text("utf-8")
    assert report.startswith(f"# {name} eval report")
    assert "cost: $0" in report


def test_cli_refuses_anthropic_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        cli.main(["--suite", "draft_units", "--provider", "anthropic"])


def test_cli_bad_ceiling_exits_2(tmp_path: Path) -> None:
    code = cli.main(["--suite", "draft_units", "--max-cost-usd", "0", "--out", str(tmp_path / "r")])
    assert code == 2
