"""The fake provider: answers without a model, for local and test only (R41).

Each task registers a responder that computes a deterministic answer from the request's
`payload`. The answer still goes through the task's output checks, like a model's would.
"""

from collections.abc import Callable, Mapping

from ai_service.llm.pricing import FAKE_MODEL
from ai_service.llm.types import AdapterResult, LlmRequest, ProviderError

Responder = Callable[[LlmRequest], str]


class FakeAdapter:
    provider = "fake"
    fixed_model: str | None = FAKE_MODEL

    def __init__(self, responders: Mapping[str, Responder]) -> None:
        self._responders = dict(responders)

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        responder = self._responders.get(request.task)
        if responder is None:
            raise ProviderError("no_responder")
        return AdapterResult(text=responder(request), input_tokens=0, output_tokens=0)
