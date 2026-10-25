"""T2.10: cost of a call, from the price table in the code (ADR-0010)."""

from decimal import Decimal

import pytest

from ai_service.llm.pricing import FAKE_MODEL, PRICES, UnknownModelPriceError, cost_usd, price_for


def test_t210_cost_comes_from_the_price_table() -> None:
    # Red when: cost ignores the table (or a token count), and quotas sum the wrong money.
    # Claude Haiku 5.5: $0.10 in / $0.50 out per million tokens (prompts up to 100k tokens).
    price = price_for("claude-haiku-5-5")
    assert cost_usd(price, input_tokens=1000, output_tokens=200) == Decimal("0.000200")


def test_t210_cost_is_a_decimal_rounded_up_to_the_micro_dollar() -> None:
    # Red when: cost is a float, or rounds down, and T2.11 quotas let many tiny calls through.
    cost = cost_usd(price_for("claude-haiku-5-5"), input_tokens=1, output_tokens=0)
    assert isinstance(cost, Decimal)
    assert cost == Decimal("0.000001")


def test_t210_long_prompts_cost_the_long_context_price() -> None:
    # Above 100k prompt tokens Haiku 5.5 costs $0.50 / $2.50: the whole call, not the excess.
    price = price_for("claude-haiku-5-5")
    assert cost_usd(price, input_tokens=200_000, output_tokens=0) == Decimal("0.100000")
    assert cost_usd(price, input_tokens=100_000, output_tokens=0) == Decimal("0.010000")


def test_t210_long_price_starts_at_the_first_token_over_100k() -> None:
    # Red when: the long-context threshold moves up by even one token (100_001 -> 100_002).
    price = price_for("claude-haiku-5-5")
    assert cost_usd(price, input_tokens=100_001, output_tokens=0) == Decimal("0.050001")


def test_t210_unknown_model_has_no_price() -> None:
    # Red when: a model missing from the table costs 0, and its calls never count to a quota.
    with pytest.raises(UnknownModelPriceError):
        price_for("claude-unknown-9")


def test_t210_fake_grader_costs_nothing() -> None:
    assert cost_usd(price_for(FAKE_MODEL), input_tokens=None, output_tokens=None) == 0


def test_t210_unknown_token_counts_cost_nothing_rather_than_failing() -> None:
    # A failed call has no usage; its row must still be written (cost 0, tokens null).
    assert cost_usd(price_for("claude-haiku-5-5"), input_tokens=None, output_tokens=None) == 0


def test_t210_every_price_is_a_decimal() -> None:
    for model, price in PRICES.items():
        assert isinstance(price.input_per_mtok, Decimal), model
        assert isinstance(price.output_per_mtok, Decimal), model
