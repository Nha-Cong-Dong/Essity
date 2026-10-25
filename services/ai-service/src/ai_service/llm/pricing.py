"""What a call costs, in USD (ADR-0010: the price table is configuration kept in the repo).

Prices change: check them against the provider's price page when adding or changing a model.
Every model the task table can pick must be here, or the service refuses to start
(`Settings.llm_models`). Costs are exact `Decimal`s rounded *up* to the micro-dollar, so many
small calls never add up to less than they cost (T2.11 quotas sum them).
"""

from dataclasses import dataclass
from decimal import ROUND_UP, Decimal

FAKE_MODEL = "fake-grader-v1"
_PER_TOKEN = Decimal(1_000_000)
_MICRO_DOLLAR = Decimal("0.000001")


class UnknownModelPriceError(LookupError):
    """A model with no price: calling it would spend money no quota counts."""


@dataclass(frozen=True)
class Price:
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    # Some models charge more for the whole call once the prompt passes a size.
    long_prompt_from_tokens: int | None = None
    long_input_per_mtok: Decimal | None = None
    long_output_per_mtok: Decimal | None = None


PRICES: dict[str, Price] = {
    # Checked 2026-10-25 (Anthropic pricing, cached in the claude-api reference): $0.10 / $0.50
    # per million tokens for prompts up to 100k tokens, $0.50 / $2.50 beyond.
    "claude-haiku-5-5": Price(
        input_per_mtok=Decimal("0.10"),
        output_per_mtok=Decimal("0.50"),
        long_prompt_from_tokens=100_001,
        long_input_per_mtok=Decimal("0.50"),
        long_output_per_mtok=Decimal("2.50"),
    ),
    FAKE_MODEL: Price(input_per_mtok=Decimal(0), output_per_mtok=Decimal(0)),
}


def price_for(model: str) -> Price:
    try:
        return PRICES[model]
    except KeyError:
        raise UnknownModelPriceError(model) from None


def cost_usd(price: Price, *, input_tokens: int | None, output_tokens: int | None) -> Decimal:
    """Cost of one call. Unknown counts (a failed call has no usage) cost nothing."""
    tokens_in = input_tokens or 0
    tokens_out = output_tokens or 0
    per_in, per_out = price.input_per_mtok, price.output_per_mtok
    long_from = price.long_prompt_from_tokens
    if long_from is not None and tokens_in >= long_from:
        per_in = price.long_input_per_mtok or per_in
        per_out = price.long_output_per_mtok or per_out
    cost = (tokens_in * per_in + tokens_out * per_out) / _PER_TOKEN
    return cost.quantize(_MICRO_DOLLAR, rounding=ROUND_UP)
