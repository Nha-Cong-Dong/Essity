"""Anthropic's Messages API through the official SDK (ADR-0010).

- One HTTP request per call: the SDK's own retries are off (`max_retries=0`). The task decides
  about a second call, and every call is written to `llm_call` (🟠1).
- The timeout is the time left before the request's deadline, passed on each call (B2).
- Instructions go in `system`, the data block in the single user message; the output is
  constrained by structured outputs (`output_config.format`), then checked again by the task.
- Thinking is off and output capped at `MAX_TOKENS` (G6): thinking tokens would count against
  the cap and the latency budget. Revisit with the eval when the model is approved (T2.12 #7).
  A task whose answer is a list (draft_units) sets its own `request.max_output_tokens`.
- Errors become `ProviderError` with a stable code. Exception messages, which can quote the
  request, are never passed on.
"""

import logging
import re
from typing import Any, cast

import anthropic
import httpx2

from ai_service.llm.types import AdapterResult, LlmRequest, ProviderError, ProviderName

_log = logging.getLogger(__name__)

MAX_TOKENS = 800

# Structured outputs refuse these JSON Schema keywords with a 400 (T7.16: the `provider_rejected`
# of chunk_units). The sizes stay in the task's own checks, which run on every reply.
_UNSUPPORTED = frozenset(
    {
        "maxLength",
        "minLength",
        "maxItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)
_ERROR_TYPE = re.compile(r"[a-z_]{1,64}")


def _supported(node: Any) -> Any:
    """A copy of a JSON Schema without the keywords the API refuses (`minItems` > 1 as well)."""
    if isinstance(node, dict):
        fields = cast("dict[str, Any]", node)
        return {
            key: _supported(value)
            for key, value in fields.items()
            if key not in _UNSUPPORTED and not (key == "minItems" and value not in (0, 1))
        }
    if isinstance(node, list):
        return [_supported(item) for item in cast("list[Any]", node)]
    return node


def _error_type(error: anthropic.APIStatusError) -> str | None:
    """Anthropic's error type (`invalid_request_error`...), never its message: that may quote
    the request."""
    body: Any = error.body
    inner = cast("dict[str, Any]", body).get("error") if isinstance(body, dict) else None
    kind = cast("dict[str, Any]", inner).get("type") if isinstance(inner, dict) else None
    return kind if isinstance(kind, str) and _ERROR_TYPE.fullmatch(kind) else None


def _content(request: LlmRequest) -> Any:
    """A plain string for text-only tasks; image blocks first, then the text, for vision."""
    if not request.images:
        return request.user
    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": i.media_type, "data": i.base64()},
        }
        for i in request.images
    ]
    blocks.append({"type": "text", "text": request.user})
    return blocks


class AnthropicAdapter:
    provider: ProviderName = "anthropic"
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
                max_tokens=request.max_output_tokens or MAX_TOKENS,
                system=request.system,
                messages=[{"role": "user", "content": _content(request)}],
                output_config={
                    "format": {"type": "json_schema", "schema": _supported(request.output_schema)}
                },
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
            _log.warning(
                "provider rejected" if code == "provider_rejected" else "provider failed",
                extra={"status": error.status_code, "error_type": _error_type(error)},
            )
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
