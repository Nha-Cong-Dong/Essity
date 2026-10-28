"""Shared pieces of the llm/ tests: a request, and Anthropic's API faked at the HTTP layer.

The real SDK runs on `httpx2.MockTransport` (no `messages.create` mock): what the tests see is
what the SDK would send over the wire.
"""

import json
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx2
from sqlalchemy.orm import Session

from ai_service.llm.types import LlmRequest

# Not shaped like a real key (gitleaks), and never sent off the machine.
FAKE_KEY = "test-anthropic-key-not-real"
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def make_request(**overrides: Any) -> LlmRequest:
    values: dict[str, Any] = {
        "task": "grade",
        "user_id": uuid.uuid4(),
        "subject_id": uuid.uuid4(),
        "pipeline_run_id": uuid.uuid4(),
        "prompt_version": "v1",
        "attempt": 1,
        "system": "Grade the answer.",
        "user": "<answer>TCP dùng bắt tay ba bước</answer>",
        "output_schema": SCHEMA,
        "payload": {"echo": "ok"},
    }
    return LlmRequest(**{**values, **overrides})


def message_json(text: str, input_tokens: int = 1000, output_tokens: int = 200) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


class FakeAnthropicApi:
    """Answers every request with `respond(request)` and keeps what it received."""

    def __init__(self, respond: Callable[[httpx2.Request], httpx2.Response]) -> None:
        self.requests: list[httpx2.Request] = []
        self._respond = respond

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self._respond(request)

    def client(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self.handler))

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


def answering(text: str = '{"ok": true}') -> FakeAnthropicApi:
    return FakeAnthropicApi(lambda _: httpx2.Response(200, json=message_json(text)))


def failing(status: int) -> FakeAnthropicApi:
    error = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
    return FakeAnthropicApi(lambda _: httpx2.Response(status, json=error))


class NoQuota:
    """A quota guard for tests not about the quota: admits every call, sets nothing aside."""

    def reserve(self, request: LlmRequest, estimate: Decimal) -> uuid.UUID | None:
        return None

    def release(self, reservation_id: uuid.UUID, session: Session | None = None) -> None:
        raise AssertionError("no reservation was made")

    def hold(self, reservation_id: uuid.UUID) -> None:
        raise AssertionError("no reservation was made")
