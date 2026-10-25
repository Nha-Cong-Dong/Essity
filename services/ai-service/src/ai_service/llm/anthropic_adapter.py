"""Anthropic's Messages API through the official SDK (ADR-0010).

- One HTTP request per call: the SDK's own retries are off (`max_retries=0`). The task decides
  about a second call, and every call is written to `llm_call` (🟠1).
- The timeout is the time left before the request's deadline, passed on each call (B2).
- Instructions go in `system`, the data block in the single user message; the output is
  constrained by structured outputs (`output_config.format`), then checked again by the task.
- Thinking is off and output capped at `MAX_TOKENS` (G6): thinking tokens would count against
  the cap and the latency budget. Revisit with the eval when the model is approved (T2.12 #7).
- Errors become `ProviderError` with a stable code. Exception messages, which can quote the
  request, are never passed on.
"""

from typing import Any

import anthropic
import httpx2

from ai_service.llm.types import AdapterResult, LlmRequest, ProviderError

MAX_TOKENS = 800


class AnthropicAdapter:
    provider = "anthropic"
    fixed_model: str | None = None

    @property
    def params(self) -> dict[str, Any]:
        return {"max_tokens": MAX_TOKENS, "thinking": {"type": "disabled"}}

    def __init__(self, api_key: str, http_client: httpx2.Client | None = None) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=0, http_client=http_client)

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        try:
            message = self._client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
                output_config={"format": {"type": "json_schema", "schema": request.output_schema}},
                thinking={"type": "disabled"},
                timeout=timeout,
            )
        except anthropic.APITimeoutError:
            raise ProviderError("timeout") from None
        except anthropic.APIConnectionError:
            raise ProviderError("connection_error") from None
        except anthropic.RateLimitError:
            raise ProviderError("rate_limited") from None
        except anthropic.APIStatusError as error:
            code = "provider_error" if error.status_code >= 500 else "provider_rejected"
            raise ProviderError(code) from None
        except anthropic.APIError:
            # A response the SDK could not read.
            raise ProviderError("provider_error") from None
        text = "".join(block.text for block in message.content if block.type == "text")
        return AdapterResult(
            text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=message.stop_reason,
        )
