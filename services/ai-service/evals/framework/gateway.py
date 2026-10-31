"""How an eval suite reaches a model: one `Gateway`, whatever the provider.

`AdapterGateway` wraps a production `Adapter` (the real run, by hand, when a key exists);
`ScriptedGateway` answers from canned replies (CI and `--provider fake`: checks the harness, not
a model). Neither retries: a call is one request.
"""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from ai_service.llm.anthropic_adapter import MAX_TOKENS
from ai_service.llm.pricing import FAKE_MODEL, Price, cost_usd, price_for
from ai_service.llm.types import Adapter, LlmRequest, ProviderName, Task

# The service's task table (llm.types.Task) has no entry for the new tasks yet; the eval borrows
# the closest one so an adapter accepts the request. Only the fake provider reads the name.
BORROWED_TASK: dict[str, Task] = {
    "draft_units": "chunk_units",
    "generate_like": "generate_questions",
    "judge_questions": "generate_questions",
    "link_question": "generate_questions",
}
_EVAL_ID = uuid.uuid5(uuid.NAMESPACE_URL, "essity-eval")
TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int | None
    output_tokens: int | None


class Prompt(Protocol):
    """What every task's prompt object has in common."""

    @property
    def system(self) -> str: ...
    @property
    def user(self) -> str: ...
    @property
    def output_schema(self) -> dict[str, Any]: ...


class Gateway(Protocol):
    @property
    def provider(self) -> ProviderName: ...
    @property
    def model(self) -> str: ...
    @property
    def price(self) -> Price: ...
    @property
    def max_tokens(self) -> int: ...

    def complete(self, task: str, prompt: Prompt) -> Completion: ...


def worst_case(gateway: Gateway, prompt: Prompt) -> Decimal:
    """A token is at most a character; the output is capped at `max_tokens`."""
    chars = len(prompt.system) + len(prompt.user) + len(json.dumps(prompt.output_schema))
    return cost_usd(gateway.price, input_tokens=chars, output_tokens=gateway.max_tokens)


class AdapterGateway:
    def __init__(self, adapter: Adapter, model: str) -> None:
        self._adapter = adapter
        self.model = model
        self.price = price_for(model)  # fails closed: an unpriced model is refused
        self.provider: ProviderName = adapter.provider
        self.max_tokens = int(adapter.params.get("max_tokens", MAX_TOKENS))

    def complete(self, task: str, prompt: Prompt) -> Completion:
        request = LlmRequest(
            task=BORROWED_TASK[task],
            user_id=_EVAL_ID,
            subject_id=_EVAL_ID,
            pipeline_run_id=_EVAL_ID,
            prompt_version="eval",
            attempt=1,
            system=prompt.system,
            user=prompt.user,
            output_schema=prompt.output_schema,
        )
        done = self._adapter.complete(request, model=self.model, timeout=TIMEOUT_SECONDS)
        return Completion(done.text, done.input_tokens, done.output_tokens)


class ScriptedGateway:
    """Replies in turn, the last one repeating; an Exception in the list is raised."""

    provider: ProviderName = "fake"
    model = FAKE_MODEL
    max_tokens = 0

    def __init__(
        self,
        replies: Sequence[str | Exception],
        *,
        price: Price | None = None,
        tokens: tuple[int, int] = (0, 0),
    ) -> None:
        self._replies = list(replies)
        self._tokens = tokens
        self.price = price or price_for(FAKE_MODEL)
        self.calls = 0

    def complete(self, task: str, prompt: Prompt) -> Completion:
        if not self._replies:
            raise LookupError("no scripted reply")
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        if isinstance(reply, Exception):
            raise reply
        return Completion(reply, *self._tokens)
