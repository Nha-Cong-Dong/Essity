"""T8.4b tester: the cost ceiling of the manual real-model eval run (budget 2 USD). Fakes only:
the adapter is replaced, no model is called."""

import json
from decimal import Decimal

import pytest

from ai_service.llm.anthropic_adapter import MAX_TOKENS
from ai_service.llm.pricing import cost_usd, price_for
from ai_service.llm.types import AdapterResult, LlmRequest
from ai_service.tasks.grade_practice import PracticePrompt
from evals.grade_practice.runner import (
    DEFAULT_CASES,
    DEFAULT_MODEL,
    load_cases,
    main,
    oracle_ask,
    run,
)


class _Adapter:
    calls = 0
    input_tokens = 10

    def __init__(self, api_key: str) -> None:
        assert api_key == "sk-test"

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        type(self).calls += 1
        return AdapterResult(
            text="{}",
            input_tokens=type(self).input_tokens,
            output_tokens=5,
            stop_reason="end_turn",
        )


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> type[_Adapter]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr("ai_service.llm.anthropic_adapter.AnthropicAdapter", _Adapter)
    _Adapter.calls, _Adapter.input_tokens = 0, 10
    return _Adapter


def test_spend_adds_up_across_calls(adapter: type[_Adapter]) -> None:
    # Budget 2 USD. Red when: what each call really cost is not added to the spend, so every call
    # is checked against an empty purse and the run goes on past the ceiling.
    adapter.input_tokens = 10_000_000  # one call reports 1 USD or more, past the 0.10 ceiling
    assert main(["--provider", "anthropic", "--max-cost-usd", "0.10"]) == 2
    assert adapter.calls == 1


def test_the_worst_case_of_a_call_counts_its_longest_reply(adapter: type[_Adapter]) -> None:
    # Budget 2 USD. Red when: the check before a call counts only the prompt, not the longest
    # reply the adapter allows, so a ceiling that holds the prompt but not the reply is passed.
    cases = load_cases(DEFAULT_CASES)
    prompts: list[PracticePrompt] = []
    oracle = oracle_ask(cases)

    def capture(prompt: PracticePrompt) -> str:
        prompts.append(prompt)
        return oracle(prompt)

    run(cases[:1], capture)
    first = prompts[0]
    size = len(first.system) + len(first.user) + len(json.dumps(first.output_schema))
    price = price_for(DEFAULT_MODEL)
    prompt_only = cost_usd(price, input_tokens=size, output_tokens=0)
    worst = cost_usd(price, input_tokens=size, output_tokens=MAX_TOKENS)
    ceiling = (prompt_only + worst) / Decimal(2)
    assert prompt_only < ceiling < worst
    assert main(["--provider", "anthropic", "--max-cost-usd", str(ceiling)]) == 2
    assert adapter.calls == 0
