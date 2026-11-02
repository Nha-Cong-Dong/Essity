"""Eval for practice grading (T8.4a, T8.4b: >= 40 labelled pairs, per-idea match >= 85%,
"graded Correct but really Incorrect" <= 5%).

    from evals.grade_practice.runner import load_cases, run
    report = run(load_cases(path), ask)

`ask` is the same callable `grade_practice` takes. CI runs the dataset only against a fake model
(`oracle_ask`, `--provider fake`, the default): it proves the harness and the labels, never the
thresholds. The thresholds are asserted by the manual run against the real model, which spends
real API budget (do it once per prompt or model change, never in CI):

    cd services/ai-service
    ANTHROPIC_API_KEY=... uv run python -m evals.grade_practice.runner --provider anthropic

It refuses to start without the key and stops before a call that could pass the ceiling (about
50 calls on claude-haiku-5-5 cost well under that). Exit code 0 when the thresholds hold, 1 when
not, 2 on a refusal. The report holds numbers and case ids, never an answer.
"""

import argparse
import json
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_service.tasks.grade import derive_overall
from ai_service.tasks.grade_models import Verdict
from ai_service.tasks.grade_practice import (
    PracticeGradeRequest,
    PracticePrompt,
    grade_practice,
)

MIN_MATCH = 0.85
CASES_MIN = 40
MAX_FALSE_CORRECT = 0.05
_TO_VERDICT: dict[str, Verdict] = {"yes": "correct", "partial": "partial", "no": "incorrect"}


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    category: Literal["bank_answer", "ai_answer", "injection"]
    question: str
    rubric: list[str] = Field(min_length=1)
    reference_answer: str
    answer: str
    expected: list[Literal["yes", "partial", "no"]] = Field(min_length=1)


@dataclass
class Report:
    ideas: int = 0
    matched: int = 0
    cases: int = 0
    false_correct: int = 0
    not_graded: list[str] = field(default_factory=list[str])

    @property
    def match_rate(self) -> float:
        return self.matched / self.ideas if self.ideas else 0.0

    @property
    def false_correct_rate(self) -> float:
        return self.false_correct / self.cases if self.cases else 0.0

    @property
    def passed(self) -> bool:
        return (
            self.cases > 0
            and not self.not_graded
            and self.match_rate >= MIN_MATCH
            and self.false_correct_rate <= MAX_FALSE_CORRECT
        )


def load_cases(path: Path) -> list[EvalCase]:
    cases = [
        EvalCase.model_validate_json(line)
        for line in path.read_text("utf-8").splitlines()
        if line.strip()
    ]
    for case in cases:
        if len(case.expected) != len(case.rubric):
            raise ValueError(f"{case.id}: expected and rubric differ in length")
    if len({c.id for c in cases}) != len(cases):
        raise ValueError("duplicate case id")
    return cases


def run(cases: list[EvalCase], ask: Callable[[PracticePrompt], str]) -> Report:
    """A case the model did not grade (failed or pending) stays in every denominator as a miss."""
    report = Report()
    for case in cases:
        report.cases += 1
        report.ideas += len(case.expected)
        result = grade_practice(
            PracticeGradeRequest(
                question=case.question,
                rubric=case.rubric,
                reference_answer=case.reference_answer,
                answer=case.answer,
            ),
            ask,
        )
        if result.status != "ok":
            report.not_graded.append(case.id)
            continue
        report.matched += sum(
            got.verdict == _TO_VERDICT[want]
            for got, want in zip(result.ideas, case.expected, strict=True)
        )
        expected_overall = derive_overall([_TO_VERDICT[w] for w in case.expected])
        if result.overall == "correct" and expected_overall == "incorrect":
            report.false_correct += 1
    return report


# --- command line --------------------------------------------------------------------------

DEFAULT_CASES = Path(__file__).resolve().parent / "cases.jsonl"
DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_MAX_COST_USD = "0.10"
CALL_TIMEOUT_S = 30.0


def oracle_ask(cases: list[EvalCase]) -> Callable[[PracticePrompt], str]:
    """A fake model that answers each case as labelled (found by the learner's answer in the
    prompt). It makes the fake run and CI exercise the harness without any model."""

    def ask(prompt: PracticePrompt) -> str:
        for case in cases:
            if case.answer in prompt.user:
                ideas = [
                    {"idea": f"R{n}", "verdict": v, "anchor": case.answer if v != "no" else None}
                    for n, v in enumerate(case.expected, start=1)
                ]
                return json.dumps({"ideas": ideas})
        raise ValueError("no case for this prompt")

    return ask


class CeilingReachedError(Exception):
    """The next call could take the spend past `--max-cost-usd`."""


def anthropic_ask(api_key: str, model: str, ceiling: Decimal) -> Callable[[PracticePrompt], str]:
    """The real model, through the service's own adapter. Each call is checked against the ceiling
    first with its worst case (a token is at most a character; output capped by the adapter)."""
    from ai_service.llm.anthropic_adapter import MAX_TOKENS, AnthropicAdapter
    from ai_service.llm.client import LlmUnavailableError
    from ai_service.llm.pricing import cost_usd, price_for
    from ai_service.llm.types import LlmRequest, ProviderError

    adapter = AnthropicAdapter(api_key)
    price = price_for(model)
    spent = Decimal(0)

    def ask(prompt: PracticePrompt) -> str:
        nonlocal spent
        worst = cost_usd(
            price,
            input_tokens=len(prompt.system)
            + len(prompt.user)
            + len(json.dumps(prompt.output_schema)),
            output_tokens=MAX_TOKENS,
        )
        if spent + worst > ceiling:
            raise CeilingReachedError
        request = LlmRequest(
            task="grade_practice",
            user_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            pipeline_run_id=uuid.uuid4(),
            prompt_version="v1",
            attempt=1,
            system=prompt.system,
            user=prompt.user,
            output_schema=prompt.output_schema,
        )
        try:
            result = adapter.complete(request, model=model, timeout=CALL_TIMEOUT_S)
        except ProviderError as error:
            raise LlmUnavailableError(error.code) from None
        spent += cost_usd(
            price, input_tokens=result.input_tokens, output_tokens=result.output_tokens
        )
        return result.text

    return ask


def parse_ceiling(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("cost ceiling must be a number") from None
    if not value.is_finite() or value <= 0:
        raise ValueError("cost ceiling must be a positive, finite number")
    return value


def render(report: Report) -> str:
    lines = [
        f"cases: {report.cases}, ideas: {report.ideas}",
        f"match: {report.match_rate:.1%} (need >= {MIN_MATCH:.0%})",
        f"false 'Đúng': {report.false_correct_rate:.1%} (need <= {MAX_FALSE_CORRECT:.0%})",
        f"not graded: {', '.join(report.not_graded) or 'none'}",
        f"result: {'PASS' if report.passed else 'FAIL'}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(prog="evals.grade_practice.runner")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--provider", choices=["fake", "anthropic"], default="fake")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-cost-usd", default=DEFAULT_MAX_COST_USD)
    args = parser.parse_args(argv)
    try:
        ceiling = parse_ceiling(args.max_cost_usd)
        cases = load_cases(args.cases)
        if args.provider == "fake":
            ask = oracle_ask(cases)
        else:
            key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not key:
                raise ValueError("ANTHROPIC_API_KEY is not set: refusing to run before any call")
            ask = anthropic_ask(key, args.model, ceiling)
        report = run(cases, ask)
    except (ValueError, LookupError, CeilingReachedError) as error:
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    out(render(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
