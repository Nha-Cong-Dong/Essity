"""FIX-CHUNK: a task may ask for a larger output cap; the stop reason reaches the task.

QA-FINAL 05/11: every `draft_units` v2 call ended with `stop_reason=max_tokens` at 800 output
tokens, so the JSON was cut and refused as `schema` on both attempts.
"""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.db.models import LlmCall, PipelineRun
from ai_service.llm.anthropic_adapter import MAX_TOKENS, AnthropicAdapter
from ai_service.llm.client import LlmClient
from ai_service.llm.types import AdapterResult, LlmRequest, ProviderName
from tests.llm.helpers import FAKE_KEY, NoQuota, answering, make_request

MODEL = "claude-haiku-5-5"
FAR = 10.0**12  # a deadline that never passes


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def run(sessions: sessionmaker[Session]) -> PipelineRun:
    with sessions() as session:
        run = PipelineRun(
            user_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            task="grade",
            prompt_version="v1",
            prompt_sha256="0" * 64,
        )
        session.add(run)
        session.commit()
        return run


def request_for(run: PipelineRun, **overrides: Any) -> LlmRequest:
    return make_request(
        user_id=run.user_id, subject_id=run.subject_id, pipeline_run_id=run.id, **overrides
    )


class RecordingQuota(NoQuota):
    def __init__(self) -> None:
        self.estimates: list[Decimal] = []

    def reserve(self, request: LlmRequest, estimate: Decimal) -> uuid.UUID | None:
        self.estimates.append(estimate)
        return None


class Truncated:
    provider: ProviderName = "anthropic"
    fixed_model: str | None = None
    params: dict[str, Any] = {"max_tokens": MAX_TOKENS}

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        return AdapterResult('{"units": [', 10, 800, stop_reason="max_tokens")


# Red when: the adapter ignores the task's cap and still sends 800 (the QA-FINAL cut JSON).
def test_fix_chunk_adapter_sends_the_requests_output_cap() -> None:
    api = answering()
    AnthropicAdapter(api_key=FAKE_KEY, http_client=api.client()).complete(
        make_request(max_output_tokens=8192), model=MODEL, timeout=5.0
    )
    assert api.body()["max_tokens"] == 8192


# Red when: a request with no cap of its own stops getting the default 800 (G6).
def test_fix_chunk_adapter_default_cap_unchanged() -> None:
    api = answering()
    AnthropicAdapter(api_key=FAKE_KEY, http_client=api.client()).complete(
        make_request(), model=MODEL, timeout=5.0
    )
    assert api.body()["max_tokens"] == 800


# Red when: the audit row or the quota estimate keep 800 while 8192 was sent: the call can no
# longer be run again as it was, and the reservation is under the worst case.
def test_fix_chunk_row_and_estimate_use_the_requests_cap(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    adapter = AnthropicAdapter(api_key=FAKE_KEY, http_client=answering().client())
    quota = RecordingQuota()
    client = LlmClient(adapter, sessions, models={"grade": MODEL}, quota_guard=quota)
    client.call(request_for(run, max_output_tokens=8192), deadline=FAR)
    client.call(request_for(run), deadline=FAR)
    with Session(engine) as session:
        rows = list(session.scalars(select(LlmCall).where(LlmCall.user_id == run.user_id)))
    assert sorted(r.input["params"]["max_tokens"] for r in rows) == [800, 8192]
    big, small = quota.estimates
    assert big - small == Decimal(8192 - 800) * Decimal("0.50") / 1_000_000


# Red when: the task cannot see that the output was cut (stop_reason lost on the way back).
def test_fix_chunk_result_carries_the_stop_reason(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    client = LlmClient(Truncated(), sessions, models={"grade": MODEL}, quota_guard=NoQuota())
    assert client.call(request_for(run), deadline=FAR).stop_reason == "max_tokens"


@pytest.mark.parametrize("cap", [0, 64_001])
def test_fix_chunk_cap_out_of_bounds_refused(cap: int) -> None:
    with pytest.raises(ValidationError):
        make_request(max_output_tokens=cap)
