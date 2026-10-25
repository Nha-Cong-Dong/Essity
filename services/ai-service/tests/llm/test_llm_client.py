"""T2.10: LlmClient writes one llm_call row per call, success or failure, in its own transaction.

Runs on the real test PostgreSQL. Rows are committed (that is the point), so each test reads
back only the rows of its own random user.
"""

import time
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.config import Settings
from ai_service.db.models import LlmCall, PipelineRun
from ai_service.llm.anthropic_adapter import AnthropicAdapter
from ai_service.llm.client import (
    AuditUnavailableError,
    LlmClient,
    LlmUnavailableError,
    QuotaGuard,
    build_adapter,
)
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.pricing import FAKE_MODEL, UnknownModelPriceError
from ai_service.llm.types import AdapterResult, LlmRequest, ProviderError, ProviderName
from tests.llm.helpers import FAKE_KEY, answering, failing, make_request

MODEL = "claude-haiku-5-5"


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def run(sessions: sessionmaker[Session]) -> PipelineRun:
    """A committed pipeline_run for a user of its own."""
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


def rows_of(engine: Engine, run: PipelineRun) -> list[LlmCall]:
    """Read through a connection of its own: only committed rows are visible."""
    with Session(engine) as session:
        query = select(LlmCall).where(LlmCall.user_id == run.user_id).order_by(LlmCall.attempt)
        return list(session.scalars(query))


def deadline(seconds: float = 9.0) -> float:
    return time.monotonic() + seconds


def fake_client(sessions: sessionmaker[Session], **kwargs: Any) -> LlmClient:
    adapter = FakeAdapter({"grade": lambda _: '{"ok": true}'})
    return LlmClient(adapter, sessions, models={"grade": MODEL}, **kwargs)


class Scripted:
    """An adapter that answers with the next scripted result, or raises it."""

    provider: ProviderName = "anthropic"
    fixed_model: str | None = None
    params: dict[str, Any] = {}

    def __init__(self, *results: AdapterResult | Exception) -> None:
        self.results = list(results)
        self.calls = 0

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_t210_each_call_writes_one_llm_call_row(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: a call is not written, and cost and "run it again" are lost (ADR-0010).
    request = request_for(run)
    result = fake_client(sessions).call(request, deadline=deadline())
    [row] = rows_of(engine, run)
    assert row.id == result.llm_call_id
    assert (row.pipeline_run_id, row.user_id, row.subject_id) == (
        run.id,
        run.user_id,
        run.subject_id,
    )
    assert (row.task, row.prompt_version, row.attempt) == ("grade", "v1", 1)
    assert row.output == '{"ok": true}' == result.text
    assert row.error_code is None
    assert row.latency_ms >= 0


def test_t210_fake_row_names_the_fake_and_costs_nothing(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: the fake's rows pass for a real model's, and core cannot refuse them (R41).
    result = fake_client(sessions).call(request_for(run), deadline=deadline())
    [row] = rows_of(engine, run)
    assert (row.provider, row.model, row.cost_usd) == ("fake", FAKE_MODEL, Decimal(0))
    assert (result.provider, result.model) == ("fake", FAKE_MODEL)


def test_t210_row_keeps_the_request_as_sent(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    request = request_for(run)
    fake_client(sessions).call(request, deadline=deadline())
    [row] = rows_of(engine, run)
    assert row.input["system"] == request.system
    assert row.input["messages"] == [{"role": "user", "content": request.user}]
    assert row.input["output_schema"] == request.output_schema
    assert row.input["params"] == {}  # the fake sends nothing else


def test_t210_row_keeps_the_provider_params_and_stop_reason(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: max_tokens/thinking are not recorded, and a call cannot be run again as it was
    # (review 🟡2); or the stop reason is lost (🟢4).
    adapter = AnthropicAdapter(api_key=FAKE_KEY, http_client=answering().client())
    LlmClient(adapter, sessions, models={"grade": MODEL}).call(
        request_for(run), deadline=deadline()
    )
    [row] = rows_of(engine, run)
    assert row.input["params"] == {"max_tokens": 800, "thinking": {"type": "disabled"}}
    assert row.stop_reason == "end_turn"


def test_t210_cost_is_computed_from_the_price_table(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    adapter = Scripted(AdapterResult(text="{}", input_tokens=1000, output_tokens=200))
    LlmClient(adapter, sessions, models={"grade": MODEL}).call(
        request_for(run), deadline=deadline()
    )
    [row] = rows_of(engine, run)
    assert (row.provider, row.model) == ("anthropic", MODEL)
    assert (row.input_tokens, row.output_tokens, row.cost_usd) == (1000, 200, Decimal("0.0002"))


def test_t210_failed_call_is_written_too(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: only successes are written, and failures vanish from the audit and the bill.
    adapter = Scripted(ProviderError("provider_error"))
    client = LlmClient(adapter, sessions, models={"grade": MODEL})
    with pytest.raises(LlmUnavailableError):
        client.call(request_for(run), deadline=deadline())
    [row] = rows_of(engine, run)
    assert (row.error_code, row.output, row.cost_usd) == ("provider_error", None, Decimal(0))


def test_t210_unexpected_failure_is_written_and_raised(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    adapter = Scripted(RuntimeError("bug in an adapter"))
    client = LlmClient(adapter, sessions, models={"grade": MODEL})
    with pytest.raises(RuntimeError):
        client.call(request_for(run), deadline=deadline())
    [row] = rows_of(engine, run)
    assert row.error_code == "internal_error"


def test_b3_audit_write_failure_is_an_error_even_after_a_good_answer(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: a grade is returned whose llm_call was never written (B3: fail closed).
    def broken() -> Session:
        session = sessions()
        session.commit = _raise  # type: ignore[method-assign]
        return session

    with pytest.raises(AuditUnavailableError):
        fake_client(broken).call(request_for(run), deadline=deadline())  # pyright: ignore[reportArgumentType]


def _raise() -> None:
    raise OSError("database is down")


def test_t210_unpriced_model_is_refused_before_the_call(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: the price is looked up after the call, and money is spent on an unpriced model.
    adapter = Scripted(AdapterResult(text="{}", input_tokens=1, output_tokens=1))
    client = LlmClient(adapter, sessions, models={"grade": "claude-unknown-9"})
    with pytest.raises(UnknownModelPriceError):
        client.call(request_for(run), deadline=deadline())
    assert adapter.calls == 0
    assert rows_of(engine, run) == []


def test_t211_quota_guard_is_asked_before_each_call(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # The hook T2.11 fills in: a guard that refuses stops the call before any money is spent.
    class Refuse(QuotaGuard):
        def check(self, request: LlmRequest) -> None:
            raise LlmUnavailableError("quota")

    adapter = Scripted(AdapterResult(text="{}", input_tokens=1, output_tokens=1))
    client = LlmClient(adapter, sessions, models={"grade": MODEL}, quota_guard=Refuse())
    with pytest.raises(LlmUnavailableError):
        client.call(request_for(run), deadline=deadline())
    assert adapter.calls == 0


def test_b2_no_call_once_the_deadline_has_passed(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    adapter = Scripted(AdapterResult(text="{}", input_tokens=1, output_tokens=1))
    client = LlmClient(adapter, sessions, models={"grade": MODEL})
    with pytest.raises(LlmUnavailableError):
        client.call(request_for(run), deadline=time.monotonic() - 0.1)
    assert adapter.calls == 0


def test_b2_adapter_gets_the_time_left(sessions: sessionmaker[Session], run: PipelineRun) -> None:
    seen: list[float] = []

    class Timed(Scripted):
        def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
            seen.append(timeout)
            return AdapterResult(text="{}", input_tokens=1, output_tokens=1)

    LlmClient(Timed(), sessions, models={"grade": MODEL}).call(
        request_for(run), deadline=deadline(4.0)
    )
    assert 3.0 < seen[0] <= 4.0


def test_o1_overloaded_api_is_one_request_one_row(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # 🟠1: the real SDK on a 529 makes exactly one HTTP request; the client writes one row.
    api = failing(529)
    adapter = AnthropicAdapter(api_key=FAKE_KEY, http_client=api.client())
    client = LlmClient(adapter, sessions, models={"grade": MODEL})
    with pytest.raises(LlmUnavailableError):
        client.call(request_for(run), deadline=deadline())
    assert len(api.requests) == 1
    [row] = rows_of(engine, run)
    assert (row.provider, row.error_code) == ("anthropic", "provider_error")


def test_t210_anthropic_end_to_end_writes_tokens_and_cost(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    api = answering('{"ok": true}')
    adapter = AnthropicAdapter(api_key=FAKE_KEY, http_client=api.client())
    LlmClient(adapter, sessions, models={"grade": MODEL}).call(
        request_for(run), deadline=deadline()
    )
    [row] = rows_of(engine, run)
    assert (row.input_tokens, row.output_tokens, row.cost_usd) == (1000, 200, Decimal("0.0002"))


# --- Choosing the adapter from settings ------------------------------------------------------


def settings(monkeypatch: pytest.MonkeyPatch, provider: str) -> Settings:
    monkeypatch.setenv("AI_LLM_PROVIDER", provider)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    return Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_t210_provider_setting_picks_the_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(build_adapter(settings(monkeypatch, "fake"), {}), FakeAdapter)
    assert isinstance(build_adapter(settings(monkeypatch, "anthropic"), {}), AnthropicAdapter)
    assert build_adapter(settings(monkeypatch, "disabled"), {}) is None
