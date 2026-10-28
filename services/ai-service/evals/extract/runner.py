"""Run the extract eval and write a Markdown report (US-02 AC6: accuracy >= 90%).

    python -m evals.extract.runner --cases evals/extract/cases.jsonl

What it measures is what production does: the same prompt, schema, retry and output rules as
`extract_session` (T4.10): `normalize_documents`, `build_llm_request`, the adapter, `check_output`
(which resolves pages in code), minus the database and the quota. Each case ends as one of
`outcome | output_invalid | provider_error`; the two errors count as a miss and stay in the
denominator, so a failing provider cannot make the numbers look better.

A case is a hit when the status matches and, for `proposed`, the day and the set of ranges
(document, FILE pages, depth, whether printed numbers were assumed to be file pages) match; for
`clarify`, the reason (and the candidate documents when the label names them) match.

The cost ceiling is checked before each call against what is spent plus the worst case of that
call; a run that would pass it stops early and the report says so (no PASS on a partial run).
The report holds numbers and case ids only: never a description or a document name.

With `--provider fake` the keyword extractor answers: that checks the harness, not a model.
The 90% figure with a real model waits for an Anthropic key (as T3.1 did).
"""

import argparse
import datetime
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, ValidationError

from ai_service.config import Settings
from ai_service.llm.anthropic_adapter import MAX_TOKENS, AnthropicAdapter
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.pricing import cost_usd, price_for
from ai_service.llm.types import Adapter, ProviderError
from ai_service.tasks.extract_session import (
    DEADLINE_SECONDS,
    RETRY_MIN_SECONDS,
    TASK,
    Outcome,
    OutputViolation,
    build_llm_request,
    check_output,
    fake_extract,
    load_prompt,
    normalize_documents,
)
from ai_service.tasks.grade import new_nonce
from evals.extract.schema import EVAL_TODAY, ExtractCase, build_request, error_reason, load_cases
from evals.grade.runner import DEFAULT_MAX_COST_USD, CeilingReachedError, parse_ceiling

MIN_ACCURACY = 0.90  # US-02 AC6

_HERE = Path(__file__).resolve().parent
DEFAULT_CASES = _HERE / "cases.jsonl"
DEFAULT_REPORT = _HERE / "out" / "report.md"  # out/ is gitignored

RunKind = Literal["outcome", "output_invalid", "provider_error"]


@dataclass(frozen=True)
class RunResult:
    kind: RunKind
    hit: bool
    got_status: str | None  # the model's status when kind is outcome
    cost: Decimal
    latency_ms: int


@dataclass(frozen=True)
class EvalResult:
    results: dict[str, RunResult]  # per case id; a case the ceiling cut off is absent
    spent: Decimal
    stopped_early: bool
    provider: str
    model: str
    model_overridden: bool
    prompt_version: str
    prompt_sha256: str


# --- model ---------------------------------------------------------------------------------


def production_model() -> str:
    """The model extraction uses in production: AI_LLM_MODELS, else the service's default."""
    raw = os.environ.get("AI_LLM_MODELS")
    models: dict[str, str] = (
        json.loads(raw)
        if raw
        else Settings.model_fields["llm_models"].get_default(call_default_factory=True)
    )
    return models[TASK]


def resolve_model(adapter: Adapter, override: str | None) -> tuple[str, bool]:
    """(model to run, whether it differs from production). Default: production's own."""
    production = adapter.fixed_model or production_model()
    if override is None or override == production:
        return production, False
    return override, True


# --- one case ------------------------------------------------------------------------------


def matches(case: ExtractCase, outcome: Outcome) -> bool:
    expected = case.expected
    if outcome.status != expected.status:
        return False
    if expected.status == "clarify":
        if outcome.reason != expected.reason:
            return False
        if expected.candidates is None:
            return True
        got = sorted(int(doc.label[1:]) - 1 for doc in outcome.candidates)
        return got == sorted(expected.candidates)
    day = None if expected.days_ago is None else EVAL_TODAY - datetime.timedelta(expected.days_ago)
    if outcome.studied_on != day:
        return False
    want = sorted((r.doc, r.start, r.end, r.depth, r.assumed_file) for r in expected.ranges)
    got = sorted(
        (int(r.doc.label[1:]) - 1, r.pages.start, r.pages.end, r.depth, r.pages.basis_assumed_file)
        for r in outcome.ranges
    )
    return got == want


def run_case(
    case: ExtractCase,
    adapter: Adapter,
    *,
    model: str,
    spent: Decimal,
    ceiling: Decimal,
) -> RunResult:
    """One try, like `extract_session`: up to two calls, the second after a broken output."""
    request = build_request(case)
    docs = normalize_documents(request)
    price = price_for(model)
    nonce = new_nonce()
    deadline = time.monotonic() + DEADLINE_SECONDS
    started = time.perf_counter()
    cost = Decimal(0)

    def result(kind: RunKind, outcome: Outcome | None = None) -> RunResult:
        latency = round((time.perf_counter() - started) * 1000)
        return RunResult(
            kind=kind,
            hit=outcome is not None and matches(case, outcome),
            got_status=outcome.status if outcome else None,
            cost=cost,
            latency_ms=latency,
        )

    for attempt in (1, 2):
        llm_request = build_llm_request(
            request, docs, run_id=uuid.uuid5(request.user_id, "run"), attempt=attempt, nonce=nonce
        )
        # A token is at most a character; the output is capped by the adapter.
        chars = len(llm_request.system) + len(llm_request.user)
        chars += len(json.dumps(llm_request.output_schema))
        worst = cost_usd(
            price,
            input_tokens=chars,
            output_tokens=int(adapter.params.get("max_tokens", MAX_TOKENS)),
        )
        if spent + cost + worst > ceiling:
            raise CeilingReachedError
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return result("provider_error")
        try:
            completed = adapter.complete(llm_request, model=model, timeout=remaining)
        except ProviderError:
            return result("provider_error")
        cost += cost_usd(
            price, input_tokens=completed.input_tokens, output_tokens=completed.output_tokens
        )
        try:
            outcome = check_output(completed.text, docs, EVAL_TODAY)
        except OutputViolation:
            if deadline - time.monotonic() < RETRY_MIN_SECONDS:
                break
            continue
        return result("outcome", outcome)
    return result("output_invalid")


# --- the whole run -------------------------------------------------------------------------


def run_eval(
    cases: list[ExtractCase],
    adapter: Adapter,
    *,
    model: str,
    max_cost_usd: Decimal = DEFAULT_MAX_COST_USD,
    model_overridden: bool = False,
) -> EvalResult:
    price_for(model)  # fail closed: an unpriced model is refused before any call
    for case in cases:
        try:
            build_request(case)  # a case the service would refuse fails here, before any money
        except ValidationError as error:
            raise ValueError(f"case {case.id}: {error_reason(error)}") from None
    prompt = load_prompt()
    results: dict[str, RunResult] = {}
    spent = Decimal(0)
    stopped = False
    try:
        for case in cases:
            run = run_case(case, adapter, model=model, spent=spent, ceiling=max_cost_usd)
            spent += run.cost
            results[case.id] = run
    except CeilingReachedError:
        stopped = True
    return EvalResult(
        results=results,
        spent=spent,
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
    complete: bool
    accuracy: float | None  # hits / all cases
    status_accuracy: float | None  # right status, whatever the details
    errors: dict[str, int]
    by_category: dict[str, tuple[int, int]]  # category -> (hits, total)
    by_status: dict[str, tuple[int, int]]  # expected status -> (hits, total)
    missed: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])


def compute_metrics(cases: list[ExtractCase], result: EvalResult) -> Metrics:
    done = [c for c in cases if c.id in result.results]
    by_category: dict[str, list[int]] = {}
    by_status: dict[str, list[int]] = {}
    missed: list[tuple[str, str, str]] = []
    status_hits = 0
    for case in done:
        run = result.results[case.id]
        status_hits += run.got_status == case.expected.status
        for table, key in ((by_category, case.category), (by_status, case.expected.status)):
            tally = table.setdefault(key, [0, 0])
            tally[0] += run.hit
            tally[1] += 1
        if not run.hit:
            missed.append((case.id, case.expected.status, run.got_status or run.kind))
    runs = list(result.results.values())
    return Metrics(
        n_cases=len(cases),
        complete=not result.stopped_early and len(done) == len(cases),
        accuracy=sum(r.hit for r in runs) / len(runs) if runs else None,
        status_accuracy=status_hits / len(done) if done else None,
        errors={
            "output_invalid": sum(r.kind == "output_invalid" for r in runs),
            "provider_error": sum(r.kind == "provider_error" for r in runs),
        },
        by_category={k: (v[0], v[1]) for k, v in by_category.items()},
        by_status={k: (v[0], v[1]) for k, v in by_status.items()},
        missed=missed,
    )


def status(value: float | None, *, complete: bool) -> str:
    """PASS or FAIL against the threshold; n/a when there is no number or the run is partial."""
    if value is None or not complete:
        return "n/a"
    return "PASS" if value >= MIN_ACCURACY else "FAIL"


# --- the report ----------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_report(metrics: Metrics, result: EvalResult) -> str:
    lines = [
        "# Extract eval report",
        "",
        f"- provider: {result.provider}, model: {result.model}",
        f"- prompt: {result.prompt_version} (sha256 {result.prompt_sha256[:12]})",
        f"- cases: {metrics.n_cases}",
        f"- cost: ${result.spent:f}",
    ]
    if result.provider == "fake":
        lines.append("- provider fake: checks the harness only, says nothing about model quality")
    if result.model_overridden:
        lines.append(f"- WARNING: model {result.model} differs from production's extract model")
    if result.stopped_early:
        lines.append(
            "- WARNING: stopped early at the cost ceiling; numbers are partial, no verdict"
        )
    lines += [
        "",
        "| Metric | Value | Threshold | Status |",
        "|---|---|---|---|",
        f"| Accuracy (US-02 AC6) | {_pct(metrics.accuracy)} | >= {MIN_ACCURACY:.0%} "
        f"| {status(metrics.accuracy, complete=metrics.complete)} |",
        f"| Right status | {_pct(metrics.status_accuracy)} | - | - |",
        "",
        "Errors (counted as a miss): "
        f"output_invalid {metrics.errors['output_invalid']}, "
        f"provider_error {metrics.errors['provider_error']}.",
        "",
        "## By category",
        "",
        "| Category | Hit | Cases |",
        "|---|---|---|",
        *(
            f"| {cat} | {hit} | {total} |"
            for cat, (hit, total) in sorted(metrics.by_category.items())
        ),
        "",
        "## By expected status",
        "",
        "| Status | Hit | Cases |",
        "|---|---|---|",
        *(f"| {st} | {hit} | {total} |" for st, (hit, total) in sorted(metrics.by_status.items())),
        "",
        "## Missed cases",
        "",
        *(
            [f"- {cid}: expected {exp}, got {got}" for cid, exp, got in metrics.missed]
            or ["- none"]
        ),
    ]
    return "\n".join(lines) + "\n"


# --- command line --------------------------------------------------------------------------


def _adapter(provider: str) -> Adapter:
    if provider == "fake":
        return FakeAdapter({TASK: fake_extract})
    key = SecretStr(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not key.get_secret_value():
        raise SystemExit("ANTHROPIC_API_KEY is not set: refusing to run before any call")
    return AnthropicAdapter(key.get_secret_value())


def main(argv: list[str] | None = None, *, out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(prog="evals.extract.runner")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--max-cost-usd", default=str(DEFAULT_MAX_COST_USD))
    parser.add_argument("--provider", choices=["fake", "anthropic"], default="fake")
    parser.add_argument("--model", default=None, help="override production's extract model")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    try:
        ceiling = parse_ceiling(args.max_cost_usd)
        cases = load_cases(args.cases)
        adapter = _adapter(args.provider)
        model, overridden = resolve_model(adapter, args.model)
        result = run_eval(
            cases, adapter, model=model, max_cost_usd=ceiling, model_overridden=overridden
        )
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
