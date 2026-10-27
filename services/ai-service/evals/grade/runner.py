"""Run the grading eval and write a Markdown report (US-05 AC4, AC5, AC6, AC7, AC9, AC10).

    python -m evals.grade.runner --cases evals/grade/cases_injection.jsonl --runs 3

What it measures is what production does: the same prompt, schema, retry and R03 checks as
`grade_answer` (T2.12), minus the database (no `pipeline_run`, no `llm_call`: an eval is not a
learner's grade). Each try of a case ends as one of
`verdict | output_invalid | provider_error`; the two errors count as a miss and as unstable, and
stay in every denominator, so a failing provider cannot make the numbers look better.

The cost ceiling is checked before each call against what is spent plus the worst case of that
call; a run that would pass it stops early and the report says so (no PASS on a partial run).
The report holds numbers and case ids only: never an answer, a source, a question or a missing
point, because T3.2 will feed real data through here.
"""

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import SecretStr

from ai_service.config import Settings
from ai_service.llm.anthropic_adapter import MAX_TOKENS, AnthropicAdapter
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.pricing import Price, cost_usd, price_for
from ai_service.llm.types import Adapter, LlmRequest, ProviderError
from ai_service.tasks.grade import (
    DEADLINE_SECONDS,
    Labels,
    OutputViolation,
    build_llm_request,
    check_output,
    fake_grade,
    load_prompt,
    new_nonce,
)
from ai_service.tasks.grade_models import (
    GradeAnchor,
    GradeQuestion,
    GradeRequest,
    GradeUnit,
    Verdict,
)
from evals.grade.schema import RIGHT_IDEA, EvalCase, load_cases

DEFAULT_RUNS = 3
DEFAULT_MAX_COST_USD = Decimal("1.00")
# US-05 AC4, AC6, AC10.
MIN_MATCH = 0.85
MAX_FALSE_CORRECT = 0.05
MIN_STABILITY = 0.95
MIN_PER_LEVEL = 15

_HERE = Path(__file__).resolve().parent
DEFAULT_CASES = _HERE / "cases_injection.jsonl"
DEFAULT_REPORT = _HERE / "out" / "report.md"  # out/ is gitignored

RunKind = Literal["verdict", "output_invalid", "provider_error"]


@dataclass(frozen=True)
class RunResult:
    kind: RunKind
    overall: Verdict | None
    units: tuple[Verdict, ...]  # in the case's order; empty unless kind is verdict
    cost: Decimal
    latency_ms: int


@dataclass(frozen=True)
class EvalResult:
    runs: int
    results: dict[str, list[RunResult]]  # per case id, the runs that finished, in order
    spent: Decimal
    stopped_early: bool
    provider: str
    model: str
    model_overridden: bool
    prompt_version: str
    prompt_sha256: str


class CeilingReachedError(Exception):
    """The next call could pass the cost ceiling."""


@dataclass
class _Budget:
    ceiling: Decimal
    spent: Decimal = Decimal(0)

    def allows(self, worst_case: Decimal) -> bool:
        return self.spent + worst_case <= self.ceiling


# --- model and ceiling ---------------------------------------------------------------------


def production_grade_model() -> str:
    """The model grading uses in production: AI_LLM_MODELS, else the service's default."""
    raw = os.environ.get("AI_LLM_MODELS")
    models: dict[str, str] = (
        json.loads(raw)
        if raw
        else Settings.model_fields["llm_models"].get_default(call_default_factory=True)
    )
    return models["grade"]


def resolve_model(adapter: Adapter, override: str | None) -> tuple[str, bool]:
    """(model to run, whether it differs from production). Default: production's own."""
    production = adapter.fixed_model or production_grade_model()
    if override is None or override == production:
        return production, False
    return override, True


def parse_ceiling(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("cost ceiling must be a number") from None
    if not value.is_finite() or value <= 0:
        raise ValueError("cost ceiling must be a positive, finite number")
    return value


# --- one case, one try ---------------------------------------------------------------------


def _id(case: EvalCase, *parts: object) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "/".join(["essity-eval", case.id, *map(str, parts)]))


def _request(case: EvalCase) -> GradeRequest:
    return GradeRequest(
        user_id=_id(case, "user"),
        subject_id=_id(case, "subject"),
        question=GradeQuestion(
            text=case.question.text,
            rubric=case.question.rubric,
            reference_answer=case.question.reference_answer,
        ),
        answer=case.answer,
        units=[
            GradeUnit(
                unit_id=_id(case, "unit", u),
                title=unit.title,
                anchors=[
                    GradeAnchor(anchor_id=_id(case, "anchor", u, a), quote_text=text)
                    for a, text in enumerate(unit.sources)
                ],
            )
            for u, unit in enumerate(case.units)
        ],
    )


def _worst_case(adapter: Adapter, price: Price, request: LlmRequest) -> Decimal:
    # A token is at most a character; the output is capped by the adapter.
    chars = len(request.system) + len(request.user)
    max_out = int(adapter.params.get("max_tokens", MAX_TOKENS))
    return cost_usd(price, input_tokens=chars, output_tokens=max_out)


def grade_case(
    case: EvalCase,
    adapter: Adapter,
    *,
    model: str,
    run: int = 0,
    budget: _Budget | None = None,
) -> RunResult:
    """One try, like `grade_answer`: up to two calls, the second after a broken output."""
    request = _request(case)
    labels = Labels.of(request)
    price = price_for(model)
    run_id = _id(case, "run", run)
    nonce = new_nonce()
    deadline = time.monotonic() + DEADLINE_SECONDS
    started = time.perf_counter()
    cost = Decimal(0)

    def result(kind: RunKind, overall: Verdict | None = None, units: tuple[Verdict, ...] = ()):
        latency = round((time.perf_counter() - started) * 1000)
        return RunResult(kind=kind, overall=overall, units=units, cost=cost, latency_ms=latency)

    for attempt in (1, 2):
        llm_request = build_llm_request(request, run_id=run_id, attempt=attempt, nonce=nonce)
        if budget is not None and not budget.allows(_worst_case(adapter, price, llm_request)):
            raise CeilingReachedError
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return result("provider_error")
        try:
            completed = adapter.complete(llm_request, model=model, timeout=remaining)
        except ProviderError:
            return result("provider_error")
        spent = cost_usd(
            price, input_tokens=completed.input_tokens, output_tokens=completed.output_tokens
        )
        cost += spent
        if budget is not None:
            budget.spent += spent
        try:
            outcome = check_output(completed.text, labels)
        except OutputViolation:
            continue
        return result("verdict", outcome.overall, tuple(u.verdict for u in outcome.units))
    return result("output_invalid")


# --- the whole run -------------------------------------------------------------------------


def run_eval(
    cases: list[EvalCase],
    adapter: Adapter,
    *,
    model: str,
    runs: int = DEFAULT_RUNS,
    max_cost_usd: Decimal = DEFAULT_MAX_COST_USD,
    model_overridden: bool = False,
) -> EvalResult:
    """Every case `runs` times, run by run, so an early stop leaves whole runs behind."""
    price_for(model)  # fail closed: an unpriced model is refused before any call
    for case in cases:
        _request(case)  # a case the service would refuse fails here, before any money is spent
    prompt = load_prompt()
    budget = _Budget(max_cost_usd)
    results: dict[str, list[RunResult]] = {case.id: [] for case in cases}
    stopped = False
    try:
        for run in range(runs):
            for case in cases:
                results[case.id].append(
                    grade_case(case, adapter, model=model, run=run, budget=budget)
                )
    except CeilingReachedError:
        stopped = True
    return EvalResult(
        runs=runs,
        results=results,
        spent=budget.spent,
        stopped_early=stopped,
        provider=adapter.provider,
        model=model,
        model_overridden=model_overridden,
        prompt_version=prompt.version,
        prompt_sha256=prompt.sha256,
    )


# --- metrics (pure) ------------------------------------------------------------------------


@dataclass(frozen=True)
class Metrics:
    n_cases: int
    runs: int
    complete: bool
    overall_match: float | None  # AC4, first run
    unit_match: float | None  # AC9, first run
    false_correct: float | None  # AC4: of the cases labelled incorrect, graded correct
    stability: float | None  # AC6
    errors: dict[str, int]
    by_category: dict[str, tuple[int, int]]  # category -> (matched, total), first run
    missed: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])
    right_idea_failed: list[str] = field(default_factory=list[str])  # AC5
    level_counts: dict[int, int] = field(default_factory=dict[int, int])  # AC10


def _ratio(hit: int, total: int) -> float | None:
    return hit / total if total else None


def compute_metrics(cases: list[EvalCase], result: EvalResult) -> Metrics:
    # Label match and the rest use the first run of each case: a later run is another look at
    # the same case, not more evidence of a match (stability is the measure across runs).
    first = {c.id: result.results[c.id][0] for c in cases if result.results.get(c.id)}
    overall_hit = unit_hit = unit_total = 0
    wrong_total = wrong_correct = 0
    by_category: dict[str, list[int]] = {}
    right_idea_failed: list[str] = []
    missed: list[tuple[str, str, str]] = []  # (case id, expected, got), first run
    for case in cases:
        run = first.get(case.id)
        if run is None:
            continue
        matched = run.kind == "verdict" and run.overall == case.expected.overall
        overall_hit += matched
        total_units = len(case.expected.units)
        unit_total += total_units
        if run.kind == "verdict":
            unit_hit += sum(g == e for g, e in zip(run.units, case.expected.units, strict=True))
        if not matched:
            missed.append((case.id, case.expected.overall, run.overall or run.kind))
        tally = by_category.setdefault(case.category, [0, 0])
        tally[0] += matched
        tally[1] += 1
        if case.expected.overall == "incorrect":
            wrong_total += 1
            wrong_correct += run.kind == "verdict" and run.overall == "correct"
        if case.category in RIGHT_IDEA and not (run.kind == "verdict" and run.overall == "correct"):
            right_idea_failed.append(case.id)

    full = [c for c in cases if len(result.results.get(c.id, [])) == result.runs]
    stable = sum(
        all(r.kind == "verdict" for r in rs) and len({r.overall for r in rs}) == 1
        for rs in (result.results[c.id] for c in full)
    )
    all_runs = [r for rs in result.results.values() for r in rs]
    return Metrics(
        n_cases=len(cases),
        runs=result.runs,
        complete=not result.stopped_early and len(full) == len(cases),
        overall_match=_ratio(overall_hit, len(first)),
        unit_match=_ratio(unit_hit, unit_total),
        false_correct=_ratio(wrong_correct, wrong_total),
        stability=_ratio(stable, len(full)),
        errors={
            "output_invalid": sum(r.kind == "output_invalid" for r in all_runs),
            "provider_error": sum(r.kind == "provider_error" for r in all_runs),
        },
        by_category={k: (v[0], v[1]) for k, v in by_category.items()},
        missed=missed,
        right_idea_failed=right_idea_failed,
        level_counts={lvl: sum(c.level == lvl for c in cases) for lvl in (1, 2, 3)},
    )


def status(value: float | None, threshold: float, *, higher_is_better: bool, complete: bool) -> str:
    """PASS or FAIL against the threshold; n/a when there is no number or the run is partial."""
    if value is None or not complete:
        return "n/a"
    ok = value >= threshold if higher_is_better else value <= threshold
    return "PASS" if ok else "FAIL"


# --- the report ----------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_report(metrics: Metrics, result: EvalResult) -> str:
    done = metrics.complete
    rows: list[tuple[str, float | None, str, str]] = [
        ("Label match, overall (AC4)", metrics.overall_match, f">= {MIN_MATCH:.0%}",
         status(metrics.overall_match, MIN_MATCH, higher_is_better=True, complete=done)),
        ("Label match, per unit (AC9)", metrics.unit_match, f">= {MIN_MATCH:.0%}",
         status(metrics.unit_match, MIN_MATCH, higher_is_better=True, complete=done)),
        ("Incorrect graded correct (AC4)", metrics.false_correct, f"<= {MAX_FALSE_CORRECT:.0%}",
         status(metrics.false_correct, MAX_FALSE_CORRECT, higher_is_better=False, complete=done)),
        (f"Stability over {metrics.runs} runs (AC6)", metrics.stability, f">= {MIN_STABILITY:.0%}",
         status(metrics.stability, MIN_STABILITY, higher_is_better=True, complete=done)),
    ]  # fmt: skip
    lines = [
        "# Grade eval report",
        "",
        f"- provider: {result.provider}, model: {result.model}",
        f"- prompt: {result.prompt_version} (sha256 {result.prompt_sha256[:12]})",
        f"- cases: {metrics.n_cases}, runs per case: {metrics.runs}",
        f"- cost: ${result.spent:f}",
    ]
    if result.provider == "fake":
        lines.append("- provider fake: checks the harness only, says nothing about model quality")
    if result.model_overridden:
        lines.append(f"- WARNING: model {result.model} differs from production's grade model")
    if result.stopped_early:
        lines.append(
            "- WARNING: stopped early at the cost ceiling; numbers are partial, no verdict"
        )
    lines += ["", "| Metric | Value | Threshold | Status |", "|---|---|---|---|"]
    lines += [
        f"| {name} | {_pct(value)} | {limit} | {state} |" for name, value, limit, state in rows
    ]
    lines += [
        "",
        "Errors (counted as a miss and as unstable): "
        f"output_invalid {metrics.errors['output_invalid']}, "
        f"provider_error {metrics.errors['provider_error']}.",
        "",
        "## By category (first run)",
        "",
        "| Category | Matched | Cases |",
        "|---|---|---|",
    ]
    lines += [
        f"| {cat} | {hit} | {total} |" for cat, (hit, total) in sorted(metrics.by_category.items())
    ]
    lines += [
        "",
        "AC5 (right idea in other words, mixed language, typos must be correct): "
        + ("all correct." if not metrics.right_idea_failed else
           "not correct: " + ", ".join(metrics.right_idea_failed)),
        "",
        "## Missed cases (first run)",
        "",
        *(
            [f"- {cid}: expected {exp}, got {got}" for cid, exp, got in metrics.missed]
            or ["- none"]
        ),
        "",
        "## Cases per question level (AC10)",
        "",
    ]  # fmt: skip
    lines += [f"- level {lvl}: {n}" for lvl, n in sorted(metrics.level_counts.items())]
    if any(n < MIN_PER_LEVEL for n in metrics.level_counts.values()):
        lines.append(f"- fewer than {MIN_PER_LEVEL} cases in a level: not yet an AC10 dataset")
    return "\n".join(lines) + "\n"


# --- command line --------------------------------------------------------------------------


def _adapter(provider: str) -> Adapter:
    if provider == "fake":
        return FakeAdapter({"grade": fake_grade})
    key = SecretStr(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not key.get_secret_value():
        raise SystemExit("ANTHROPIC_API_KEY is not set: refusing to run before any call")
    return AnthropicAdapter(key.get_secret_value())


def main(argv: list[str] | None = None, *, out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(prog="evals.grade.runner")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--max-cost-usd", default=str(DEFAULT_MAX_COST_USD))
    parser.add_argument("--provider", choices=["fake", "anthropic"], default="fake")
    parser.add_argument("--model", default=None, help="override production's grade model")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    try:
        ceiling = parse_ceiling(args.max_cost_usd)
        cases = load_cases(args.cases)
        adapter = _adapter(args.provider)
        model, overridden = resolve_model(adapter, args.model)
        result = run_eval(
            cases, adapter, model=model, runs=args.runs, max_cost_usd=ceiling,
            model_overridden=overridden,
        )  # fmt: skip
    except (ValueError, LookupError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    report = render_report(compute_metrics(cases, result), result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    out(f"report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
