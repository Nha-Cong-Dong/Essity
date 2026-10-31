"""The shared eval runner (T9.7a), after the T3.1 pattern: JSONL cases, a cost ceiling per run,
one outcome per case, a Markdown report.

A suite scores one case with the task's own pure function and an `ask` that goes through the
gateway. Around it the runner guarantees what no suite should repeat:

- the ceiling is checked before each call against what is spent plus that call's worst case; a
  run that would pass it stops and the report says so (no verdict on a partial run);
- whatever one case raises is that case's error (the class name only, never its text, which may
  hold a learner's words) and the run goes on; an error stays in every denominator as a miss;
- thresholds are a field of the suite, `None` until the first real data exists.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_service.llm.pricing import cost_usd
from evals.framework.gateway import Gateway, Prompt, worst_case

DEFAULT_MAX_COST_USD = Decimal("1.00")
UNSET = "unset (to be set when the first data exists)"

Counts = dict[str, tuple[int, int]]  # metric -> (numerator, denominator)


class CeilingReachedError(Exception):
    """The next call could pass the cost ceiling."""


class EvalCase(BaseModel):
    """Base of every suite's case: an id and, for the fake provider only, canned replies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    fake_replies: list[str] = []


@dataclass(frozen=True)
class Scored:
    hit: bool
    counts: Counts = field(default_factory=Counts)


class CostGuard:
    def __init__(self, ceiling: Decimal) -> None:
        self.ceiling = ceiling
        self.spent = Decimal(0)
        self.tripped = False

    def check(self, worst: Decimal) -> None:
        if self.spent + worst > self.ceiling:
            self.tripped = True
            raise CeilingReachedError


class GuardedAsk:
    """The `ask` a task receives: ceiling check, one gateway call, cost booked."""

    def __init__(self, gateway: Gateway, guard: CostGuard, task: str) -> None:
        self._gateway = gateway
        self._guard = guard
        self._task = task

    def __call__(self, prompt: Any) -> str:
        typed: Prompt = prompt
        self._guard.check(worst_case(self._gateway, typed))
        done = self._gateway.complete(getattr(prompt, "task", self._task), typed)
        self._guard.spent += cost_usd(
            self._gateway.price, input_tokens=done.input_tokens, output_tokens=done.output_tokens
        )
        return done.text


def _no_check[C](cases: list[C]) -> None:
    return None


@dataclass(frozen=True)
class Suite[C: EvalCase]:
    name: str
    case_model: type[C]
    task: str
    score: Callable[[C, GuardedAsk], Scored]
    thresholds: dict[str, float | None]  # metric -> minimum; None until data exists
    check_labels: Callable[[list[C]], None] = _no_check  # checks across the whole file


@dataclass(frozen=True)
class Outcome:
    scored: Scored | None  # None: the case raised
    error: str | None  # exception class name
    cost: Decimal


@dataclass(frozen=True)
class SuiteResult:
    suite: str
    outcomes: dict[str, Outcome]  # per case id; a case the ceiling cut off is absent
    n_cases: int
    spent: Decimal
    stopped_early: bool
    provider: str
    model: str


def parse_ceiling(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("cost ceiling must be a number") from None
    if not value.is_finite() or value <= 0:
        raise ValueError("cost ceiling must be a positive, finite number")
    return value


def load_cases[C: EvalCase](suite: Suite[C], path: Path) -> list[C]:
    cases: list[C] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = suite.case_model.model_validate(json.loads(line))
        except json.JSONDecodeError:
            raise ValueError(f"{path.name} line {number}: not valid JSON") from None
        except ValidationError as error:
            # Never echo the input: a case may hold a learner's text.
            why = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
            raise ValueError(f"{path.name} line {number}: {why}") from None
        if case.id in seen:
            raise ValueError(f"{path.name} line {number}: duplicate id {case.id}")
        seen.add(case.id)
        cases.append(case)
    suite.check_labels(cases)
    return cases


def run_suite[C: EvalCase](
    suite: Suite[C],
    cases: list[C],
    gateway_for: Callable[[C], Gateway],
    *,
    max_cost_usd: Decimal = DEFAULT_MAX_COST_USD,
) -> SuiteResult:
    guard = CostGuard(max_cost_usd)
    outcomes: dict[str, Outcome] = {}
    provider, model = "fake", ""
    for case in cases:
        gateway = gateway_for(case)
        provider, model = gateway.provider, gateway.model
        before = guard.spent
        scored: Scored | None = None
        error: str | None = None
        try:
            scored = suite.score(case, GuardedAsk(gateway, guard, suite.task))
        except CeilingReachedError:
            break
        except Exception as caught:  # noqa: BLE001 - whatever one case raises, the run goes on
            error = type(caught).__name__
        if guard.tripped:  # a task may swallow the signal; the run still stops
            break
        outcomes[case.id] = Outcome(scored, error, guard.spent - before)
    return SuiteResult(
        suite=suite.name,
        outcomes=outcomes,
        n_cases=len(cases),
        spent=guard.spent,
        stopped_early=guard.tripped,
        provider=provider,
        model=model,
    )


# --- metrics and report (pure) -------------------------------------------------------------


@dataclass(frozen=True)
class Metrics:
    complete: bool
    hit_rate: float | None  # hits / cases run; an error is a miss
    errors: int
    rates: dict[str, float | None]
    missed: list[str]


def compute_metrics(result: SuiteResult) -> Metrics:
    runs = result.outcomes
    sums: dict[str, list[int]] = {}
    for outcome in runs.values():
        if outcome.scored is None:
            continue
        for key, (num, den) in outcome.scored.counts.items():
            tally = sums.setdefault(key, [0, 0])
            tally[0] += num
            tally[1] += den
    hits = sum(1 for o in runs.values() if o.scored is not None and o.scored.hit)
    return Metrics(
        complete=not result.stopped_early and len(runs) == result.n_cases,
        hit_rate=hits / len(runs) if runs else None,
        errors=sum(1 for o in runs.values() if o.error is not None),
        rates={k: (v[0] / v[1] if v[1] else None) for k, v in sums.items()},
        missed=[
            cid
            for cid, o in runs.items()
            if o.error is not None or (o.scored is not None and not o.scored.hit)
        ],
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _verdict(value: float | None, minimum: float | None, *, complete: bool) -> str:
    if minimum is None or value is None or not complete:
        return "n/a"
    return "PASS" if value >= minimum else "FAIL"


def render_report(suite: Suite[Any], result: SuiteResult) -> str:
    metrics = compute_metrics(result)
    lines = [
        f"# {suite.name} eval report",
        "",
        f"- provider: {result.provider}, model: {result.model}",
        f"- cases: {result.n_cases}, run: {len(result.outcomes)}",
        f"- cost: ${result.spent:f}",
    ]
    if result.provider == "fake":
        lines.append("- provider fake: checks the harness only, says nothing about model quality")
    if result.stopped_early:
        lines.append(
            "- WARNING: stopped early at the cost ceiling; numbers are partial, no verdict"
        )
    lines += [
        "",
        "| Metric | Value | Threshold | Status |",
        "|---|---|---|---|",
        f"| Cases hit | {_pct(metrics.hit_rate)} | - | - |",
    ]
    for name in sorted(set(suite.thresholds) | set(metrics.rates)):
        minimum = suite.thresholds.get(name)
        value = metrics.rates.get(name)
        threshold = UNSET if minimum is None else f">= {minimum:.0%}"
        status = _verdict(value, minimum, complete=metrics.complete)
        lines.append(f"| {name} | {_pct(value)} | {threshold} | {status} |")
    lines += [
        "",
        f"Errors (counted as a miss): {metrics.errors}.",
        "",
        "## Missed cases",
        "",
        *([f"- {cid}" for cid in metrics.missed] or ["- none"]),
    ]
    return "\n".join(lines) + "\n"
