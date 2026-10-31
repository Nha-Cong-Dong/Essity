"""LlmClient: the one way a task calls a model (ADR-0010).

Every call, success or failure, writes one `llm_call` row in a transaction of its own (🟠4)
before the result goes back to the task. If that write fails the call's result is not used:
`AuditUnavailableError` (B3, fail closed). Order of a call:

1. the price of the model (an unpriced model is refused before any money is spent);
2. the quota guard (T2.11): the worst-case cost of the call is reserved, or the call is refused;
3. the deadline (no time left: no call);
4. one request through the adapter, with the time left as its timeout (B2);
5. the `llm_call` row (and the reservation's release, in the same transaction), then the result
   or the error. If a call was made but its spend is not recorded, the reservation is kept.
"""

import logging
import time
import uuid
from collections.abc import Mapping

from ai_service.config import Settings
from ai_service.db.models import LlmCall
from ai_service.db.session import SessionFactory
from ai_service.llm.anthropic_adapter import AnthropicAdapter
from ai_service.llm.fake_adapter import FakeAdapter, Responder
from ai_service.llm.pricing import Price, cost_usd, price_for
from ai_service.llm.quota import QuotaGuard, QuotaUnavailableError, estimate_cost
from ai_service.llm.types import (
    Adapter,
    AdapterResult,
    LlmRequest,
    LlmResult,
    ProviderError,
    ProviderName,
)

_log = logging.getLogger(__name__)


class LlmUnavailableError(Exception):
    """No usable answer from the provider: error, timeout, deadline passed. `code` is stable."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AuditUnavailableError(Exception):
    """The audit row could not be written; the call's result must not be used (B3)."""


# Provider errors after which the provider has certainly not charged (it refused the request).
# Any other failure may have been billed without usage to count: its reservation is kept.
_NOT_CHARGED = frozenset({"rate_limited", "provider_error", "provider_rejected", "no_responder"})


class LlmClient:
    def __init__(
        self,
        adapter: Adapter,
        sessions: SessionFactory,
        *,
        models: Mapping[str, str],
        quota_guard: QuotaGuard,
    ) -> None:
        self._adapter = adapter
        self._sessions = sessions
        self._models = dict(models)
        self._quota_guard = quota_guard

    @property
    def provider(self) -> ProviderName:
        return self._adapter.provider

    def call(self, request: LlmRequest, *, deadline: float) -> LlmResult:
        """One call to the model; `deadline` is a `time.monotonic()` value."""
        model = self._adapter.fixed_model or self._models[request.task]
        price = price_for(model)
        estimate = estimate_cost(price, request, self._adapter.params)
        try:
            reservation = self._quota_guard.reserve(request, estimate)
        except QuotaUnavailableError as error:
            raise AuditUnavailableError from error
        result: AdapterResult | None = None
        error_code: str | None = None
        called = settled = False
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LlmUnavailableError("deadline")

            started = time.perf_counter()
            called = True
            try:
                result = self._adapter.complete(request, model=model, timeout=remaining)
            except ProviderError as error:
                error_code = error.code
            except Exception:
                self._write(request, model, None, "internal_error", started, price)
                raise
            charged = result is not None or error_code in _NOT_CHARGED
            call_id = self._write(
                request, model, result, error_code, started, price, reservation if charged else None
            )
            settled = charged
        finally:
            if reservation is not None and not settled:
                if called:
                    self._quota_guard.hold(reservation)
                else:
                    self._quota_guard.release(reservation)
        if result is None:
            raise LlmUnavailableError(error_code or "provider_error")
        return LlmResult(text=result.text, llm_call_id=call_id, provider=self.provider, model=model)

    def _write(
        self,
        request: LlmRequest,
        model: str,
        result: AdapterResult | None,
        error_code: str | None,
        started: float,
        price: Price,
        reservation: uuid.UUID | None = None,
    ) -> uuid.UUID:
        latency_ms = round((time.perf_counter() - started) * 1000)
        row = LlmCall(
            pipeline_run_id=request.pipeline_run_id,
            user_id=request.user_id,
            subject_id=request.subject_id,
            task=request.task,
            provider=self.provider,
            model=model,
            prompt_version=request.prompt_version,
            attempt=request.attempt,
            input={
                "system": request.system,
                "messages": [{"role": "user", "content": request.user}],
                "images": [{"sha256": i.sha256, "bytes": len(i.data)} for i in request.images],
                "output_schema": request.output_schema,
                "params": self._adapter.params,
            },
            output=result.text if result else None,
            stop_reason=result.stop_reason if result else None,
            input_tokens=result.input_tokens if result else None,
            output_tokens=result.output_tokens if result else None,
            cost_usd=cost_usd(
                price,
                input_tokens=result.input_tokens if result else None,
                output_tokens=result.output_tokens if result else None,
            ),
            latency_ms=latency_ms,
            error_code=error_code,
        )
        try:
            with self._sessions() as session:
                session.add(row)
                if reservation is not None:
                    self._quota_guard.release(reservation, session)
                session.commit()
        except Exception as error:
            _log.exception("llm_call not written", extra={"provider": self.provider})
            raise AuditUnavailableError from error
        _log.info(
            "llm call",
            extra={
                "llm_call_id": str(row.id),
                "provider": self.provider,
                "attempt": request.attempt,
                "outcome": error_code or "ok",
                "duration_ms": latency_ms,
            },
        )
        return row.id


def build_adapter(settings: Settings, fake_responders: Mapping[str, Responder]) -> Adapter | None:
    """The adapter for `AI_LLM_PROVIDER`; None when grading is disabled."""
    match settings.llm_provider:
        case "fake":
            return FakeAdapter(fake_responders)
        case "anthropic":
            key = settings.anthropic_api_key
            assert key is not None  # Settings refuses anthropic without a key
            return AnthropicAdapter(api_key=key.get_secret_value())
        case "disabled":
            return None
