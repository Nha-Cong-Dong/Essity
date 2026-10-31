"""Run one suite and write its Markdown report.

    python -m evals.framework.cli --suite draft_units
    python -m evals.framework.cli --suite generate_similar --out ../../docs/evals/generate.md

`--provider fake` (the default) answers each case from its `fake_replies`: it checks the harness,
not a model. `--provider anthropic` needs `ANTHROPIC_API_KEY` and is run by hand, with the cost
ceiling below (the MVP's whole AI budget is small: never raise it casually).
"""

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from ai_service.llm.anthropic_adapter import AnthropicAdapter
from evals.draft_units.suite import SUITE as DRAFT_UNITS
from evals.framework.gateway import AdapterGateway, Gateway, ScriptedGateway
from evals.framework.runner import (
    DEFAULT_MAX_COST_USD,
    EvalCase,
    Suite,
    load_cases,
    parse_ceiling,
    render_report,
    run_suite,
)
from evals.generate_similar.suite import SUITE as GENERATE_SIMILAR
from evals.link_question.suite import SUITE as LINK_QUESTION

_EVALS = Path(__file__).resolve().parents[1]
SUITES: dict[str, Suite[Any]] = {s.name: s for s in (DRAFT_UNITS, GENERATE_SIMILAR, LINK_QUESTION)}
DEFAULT_MODEL = "claude-haiku-5-5"


def default_cases(name: str) -> Path:
    return _EVALS / name / "cases.jsonl"


def default_report(name: str) -> Path:
    return _EVALS / name / "out" / "report.md"  # out/ is gitignored


def _gateway_factory(provider: str, model: str | None) -> Callable[[EvalCase], Gateway]:
    if provider == "fake":
        return lambda case: ScriptedGateway(case.fake_replies)
    key = SecretStr(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not key.get_secret_value():
        raise SystemExit("ANTHROPIC_API_KEY is not set: refusing to run before any call")
    gateway = AdapterGateway(AnthropicAdapter(key.get_secret_value()), model or DEFAULT_MODEL)
    return lambda case: gateway


def main(argv: list[str] | None = None, *, out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(prog="evals.framework.cli")
    parser.add_argument("--suite", choices=sorted(SUITES), required=True)
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument("--max-cost-usd", default=str(DEFAULT_MAX_COST_USD))
    parser.add_argument("--provider", choices=["fake", "anthropic"], default="fake")
    parser.add_argument("--model", default=None, help=f"default {DEFAULT_MODEL}")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    suite = SUITES[args.suite]
    try:
        ceiling = parse_ceiling(args.max_cost_usd)
        cases = load_cases(suite, args.cases or default_cases(suite.name))
        gateway_for = _gateway_factory(args.provider, args.model)
        result = run_suite(suite, cases, gateway_for, max_cost_usd=ceiling)
    except (ValueError, LookupError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    target = args.out or default_report(suite.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_report(suite, result), encoding="utf-8")
    out(f"report written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
