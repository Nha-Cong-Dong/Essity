"""Inputs and outputs of the llm/ layer (ADR-0010: Pydantic in, Pydantic out)."""

import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

Task = Literal["grade", "extract_session"]
# The providers a call can go to (CHECK provider_known on llm_call).
ProviderName = Literal["anthropic", "fake"]
TASKS: tuple[Task, ...] = ("grade", "extract_session")


class LlmRequest(BaseModel):
    """One call to a model, as a task builds it.

    `system` holds the instructions only; `user` holds the data, already wrapped and escaped
    by the task (ADR-0010: untrusted text never sits with the instructions). `payload` is the
    task's structured input for the fake provider; it is never sent to a real one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: Task
    # Required, all three: a call made for nobody reaches no user's quota or audit (T2.10).
    user_id: uuid.UUID
    subject_id: uuid.UUID
    pipeline_run_id: uuid.UUID
    prompt_version: str = Field(min_length=1)
    # 1 for the first call of a run, 2 for the retry after an output that broke the rules.
    attempt: int = Field(ge=1, le=2)
    system: str
    user: str
    output_schema: dict[str, Any]
    payload: dict[str, Any] = Field(default_factory=dict[str, Any])


@dataclass(frozen=True)
class AdapterResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    stop_reason: str | None = None


@dataclass(frozen=True)
class LlmResult:
    text: str
    llm_call_id: uuid.UUID
    provider: ProviderName
    model: str


class ProviderError(Exception):
    """The provider failed or could not be reached. `code` is stable and safe to store or log:
    timeout, connection_error, rate_limited, provider_error, provider_rejected, no_responder."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Adapter(Protocol):
    """One provider. Makes exactly one request per `complete` (no retries of its own)."""

    @property
    def provider(self) -> ProviderName: ...

    # A model the adapter always uses, whatever the task table says (the fake), or None.
    @property
    def fixed_model(self) -> str | None: ...

    # Constant request parameters besides the prompt (max_tokens, thinking, ...), written to
    # llm_call so a call can be run again exactly as it was.
    @property
    def params(self) -> dict[str, Any]: ...

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult: ...
