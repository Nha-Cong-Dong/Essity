"""T2.11: a per-user cost quota, asked before every LLM call (ADR-0010, PLAN T2.11).

Runs on the real test PostgreSQL. Each test uses a user of its own, so a shared database is fine.
"""

import logging
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.config import Settings
from ai_service.db.models import LlmCall, LlmReservation, PipelineRun
from ai_service.llm.client import AuditUnavailableError, LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.pricing import FAKE_MODEL, price_for
from ai_service.llm.quota import (
    DbQuotaGuard,
    QuotaExceededError,
    QuotaLimits,
    estimate_cost,
)
from ai_service.llm.types import AdapterResult, LlmRequest, ProviderError, ProviderName
from tests.llm.helpers import make_request

MODEL = "claude-haiku-5-5"
LIMITS = QuotaLimits(daily=Decimal("1.00"), monthly=Decimal("10.00"), hard_cap_factor=Decimal(3))
OK = AdapterResult(text="{}", input_tokens=10, output_tokens=10)


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def new_run(sessions: sessionmaker[Session]) -> PipelineRun:
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


@pytest.fixture
def run(sessions: sessionmaker[Session]) -> PipelineRun:
    return new_run(sessions)


class Scripted:
    """An anthropic-looking adapter; `max_tokens` sets the worst-case estimate (0.5 USD per 1M)."""

    provider: ProviderName = "anthropic"
    fixed_model: str | None = None

    def __init__(
        self, *results: AdapterResult | Exception, max_tokens: int = 100, delay: float = 0.0
    ) -> None:
        self.results = list(results)
        self.calls = 0
        self.delay = delay
        self.params: dict[str, Any] = {"max_tokens": max_tokens}

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        self.calls += 1
        time.sleep(self.delay)
        result = self.results.pop(0) if self.results else OK
        if isinstance(result, Exception):
            raise result
        return result


def request_for(run: PipelineRun, **overrides: Any) -> LlmRequest:
    return make_request(
        user_id=run.user_id, subject_id=run.subject_id, pipeline_run_id=run.id, **overrides
    )


def guard_for(
    sessions: sessionmaker[Session],
    limits: QuotaLimits = LIMITS,
    hard_cap_tasks: frozenset[str] = frozenset({"grade"}),
) -> DbQuotaGuard:
    return DbQuotaGuard(sessions, limits, hard_cap_tasks=hard_cap_tasks)


def client_for(
    adapter: Scripted, sessions: sessionmaker[Session], guard: DbQuotaGuard
) -> LlmClient:
    return LlmClient(adapter, sessions, models={"grade": MODEL}, quota_guard=guard)


def spend(
    sessions: sessionmaker[Session], run: PipelineRun, usd: str, when: datetime | None = None
) -> None:
    """A past call that cost `usd`, at `when` (default: now)."""
    with sessions() as session:
        session.add(
            LlmCall(
                pipeline_run_id=run.id,
                user_id=run.user_id,
                subject_id=run.subject_id,
                task="grade",
                provider="anthropic",
                model=MODEL,
                prompt_version="v1",
                attempt=1,
                input={},
                cost_usd=Decimal(usd),
                latency_ms=1,
                created_at=when or datetime.now(UTC),
            )
        )
        session.commit()


def deadline() -> float:
    return time.monotonic() + 9.0


def reservations_of(engine: Engine, run: PipelineRun) -> list[LlmReservation]:
    with Session(engine) as session:
        return list(
            session.scalars(select(LlmReservation).where(LlmReservation.user_id == run.user_id))
        )


def today_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


# --- Windows: under, over the soft limit, over the hard cap ----------------------------------


def test_t211_under_the_limit_every_task_passes(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: the guard refuses a user who is under the limit.
    spend(sessions, run, "0.10")
    for hard_cap_tasks in (frozenset({"grade"}), frozenset[str]()):
        guard_for(sessions, hard_cap_tasks=hard_cap_tasks).reserve(
            request_for(run), Decimal("0.01")
        )


def test_t211_over_the_soft_limit_grading_still_runs(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # ADR-0010 / US-12 AC9: grading goes on past the normal limit, up to the hard cap.
    spend(sessions, run, "1.50")
    guard_for(sessions).reserve(request_for(run), Decimal("0.01"))


def test_t211_over_the_soft_limit_other_tasks_are_deferred(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: a task outside the hard-cap set (document indexing) is held to the hard cap.
    spend(sessions, run, "1.50")
    with pytest.raises(QuotaExceededError) as info:
        guard_for(sessions, hard_cap_tasks=frozenset()).reserve(request_for(run), Decimal("0.01"))
    assert (info.value.hard, info.value.window) == (False, "day")


def test_t211_over_the_hard_cap_grading_is_refused_with_a_neutral_error(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    spend(sessions, run, "3.00")  # daily 1.00 x 3
    with pytest.raises(QuotaExceededError) as info:
        guard_for(sessions).reserve(request_for(run), Decimal("0.01"))
    assert (info.value.hard, info.value.window) == (True, "day")
    assert not any(ch.isdigit() for ch in str(info.value))  # no amounts in the message


def test_t211_month_window_limits_when_the_day_is_fine(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Spent yesterday counts for the month only; skip on the 1st (yesterday is last month).
    if datetime.now(UTC).day == 1:
        pytest.skip("yesterday is not in this month")
    spend(sessions, run, "9.90", today_start() - timedelta(seconds=1))
    guard_for(sessions).reserve(request_for(run), Decimal("0.05"))
    with pytest.raises(QuotaExceededError) as info:
        guard_for(sessions, hard_cap_tasks=frozenset()).reserve(request_for(run), Decimal("0.20"))
    assert info.value.window == "month"


def test_t211_the_day_window_resets_at_utc_midnight(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    spend(sessions, run, "5.00", today_start() - timedelta(seconds=1))
    limits = QuotaLimits(Decimal("1"), Decimal("100"), Decimal(3))
    guard_for(sessions, limits, frozenset()).reserve(request_for(run), Decimal("0.01"))


def test_t211_other_users_spend_is_ignored(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    spend(sessions, new_run(sessions), "50.00")
    guard_for(sessions, hard_cap_tasks=frozenset()).reserve(request_for(run), Decimal("0.01"))


def test_t211_the_estimate_counts_before_any_money_is_spent(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: the quota is checked after the call: a big prompt spends past the cap first.
    adapter = Scripted(max_tokens=4_000_000)  # worst case 2.00 USD
    client = client_for(adapter, sessions, guard_for(sessions, hard_cap_tasks=frozenset()))
    with pytest.raises(QuotaExceededError):
        client.call(request_for(run), deadline=deadline())
    assert adapter.calls == 0
    assert reservations_of(engine, run) == []


def test_t211_estimate_is_the_worst_case_of_the_request() -> None:
    request = make_request()
    est = estimate_cost(price_for(MODEL), request, {"max_tokens": 1_000_000})
    assert Decimal("0.50") <= est < Decimal("0.51")
    assert estimate_cost(price_for(FAKE_MODEL), request, {}) == 0


# --- The race: requests at once never pass the cap together ----------------------------------


def test_t211_concurrent_calls_never_exceed_the_cap(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: read-then-call without a lock: all 8 read "nothing spent" and all 8 call.
    limits = QuotaLimits(Decimal("1.00"), Decimal("10.00"), Decimal(1))
    adapter = Scripted(max_tokens=600_000, delay=0.6)  # 0.30 each: 3 fit under 1.00
    client = client_for(adapter, sessions, guard_for(sessions, limits))
    barrier = threading.Barrier(8)
    outcomes: list[str] = []

    def one() -> None:
        barrier.wait()
        try:
            client.call(request_for(run), deadline=deadline())
            outcomes.append("ok")
        except QuotaExceededError:
            outcomes.append("refused")

    threads = [threading.Thread(target=one) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["ok"] * 3 + ["refused"] * 5
    assert adapter.calls == 3
    assert reservations_of(engine, run) == []


# --- Reservations ----------------------------------------------------------------------------


def test_t211_reservation_is_released_after_a_recorded_call(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    client = client_for(Scripted(), sessions, guard_for(sessions))
    client.call(request_for(run), deadline=deadline())
    assert reservations_of(engine, run) == []


@pytest.mark.parametrize("code", ["rate_limited", "provider_error", "provider_rejected"])
def test_t211_reservation_is_released_when_the_provider_certainly_did_not_charge(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun, code: str
) -> None:
    client = client_for(Scripted(ProviderError(code)), sessions, guard_for(sessions))
    with pytest.raises(Exception, match=code):
        client.call(request_for(run), deadline=deadline())
    assert reservations_of(engine, run) == []


def test_t211_reservation_is_kept_when_the_spend_is_unrecorded(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Review 🟠1. Red when: a timeout (the provider may have charged, no usage) frees the
    # reservation, and the next call sees the spend as zero.
    guard = guard_for(sessions, QuotaLimits(Decimal("1.00"), Decimal("10.00"), Decimal(1)))
    adapter = Scripted(ProviderError("timeout"), max_tokens=1_200_000)  # 0.60 each
    client = client_for(adapter, sessions, guard)
    with pytest.raises(Exception, match="timeout"):
        client.call(request_for(run), deadline=deadline())
    [held] = reservations_of(engine, run)
    assert held.expires_at > datetime.now(UTC) + timedelta(hours=1)
    with pytest.raises(QuotaExceededError):
        client.call(request_for(run), deadline=deadline())  # 0.60 held + 0.60 > 1.00
    assert adapter.calls == 1


def test_t211_reservation_is_kept_when_the_audit_row_cannot_be_written(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Review 🟠1: the money was spent but llm_call has no row, so the hold stays.
    def broken() -> Session:
        raise RuntimeError("database down")

    client = LlmClient(Scripted(), broken, models={"grade": MODEL}, quota_guard=guard_for(sessions))
    with pytest.raises(AuditUnavailableError):
        client.call(request_for(run), deadline=deadline())
    [held] = reservations_of(engine, run)
    assert held.expires_at > datetime.now(UTC) + timedelta(hours=1)


def test_t211_reservation_is_released_when_no_call_was_made(
    engine: Engine, sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    adapter = Scripted()
    client = client_for(adapter, sessions, guard_for(sessions))
    with pytest.raises(Exception, match="deadline"):
        client.call(request_for(run), deadline=time.monotonic() - 1)
    assert adapter.calls == 0
    assert reservations_of(engine, run) == []


def test_t211_an_expired_reservation_is_ignored(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    # Red when: a process that died mid-call locks part of the quota for ever.
    with sessions() as session:
        session.add(
            LlmReservation(
                user_id=run.user_id,
                amount_usd=Decimal("5.00"),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        session.commit()
    guard_for(sessions, hard_cap_tasks=frozenset()).reserve(request_for(run), Decimal("0.01"))


def test_t211_database_error_fails_closed(run: PipelineRun) -> None:
    # Red when: the guard cannot read the spend and lets the call through anyway.
    def broken() -> Session:
        raise RuntimeError("database down")

    adapter = Scripted()
    client = LlmClient(
        adapter,
        broken,
        models={"grade": MODEL},
        quota_guard=DbQuotaGuard(broken, LIMITS, hard_cap_tasks=frozenset({"grade"})),
    )
    with pytest.raises(AuditUnavailableError):
        client.call(request_for(run), deadline=deadline())
    assert adapter.calls == 0


def test_t211_the_fake_provider_goes_through_the_guard_too(
    sessions: sessionmaker[Session], run: PipelineRun
) -> None:
    spend(sessions, run, "3.50")  # over the hard cap
    client = LlmClient(
        FakeAdapter({"grade": lambda _: "{}"}),
        sessions,
        models={"grade": MODEL},
        quota_guard=guard_for(sessions),
    )
    with pytest.raises(QuotaExceededError):
        client.call(request_for(run), deadline=deadline())


def test_t211_client_needs_a_quota_guard(sessions: sessionmaker[Session]) -> None:
    # Review 🟡: no default guard that lets everything through.
    with pytest.raises(TypeError):
        LlmClient(Scripted(), sessions, models={"grade": MODEL})  # pyright: ignore[reportCallIssue]


# --- Warning at 80% --------------------------------------------------------------------------


def test_t211_near_the_limit_warns_once_without_amounts(
    sessions: sessionmaker[Session], run: PipelineRun, caplog: pytest.LogCaptureFixture
) -> None:
    spend(sessions, run, "0.85")
    guard = guard_for(sessions)
    with caplog.at_level(logging.WARNING, logger="ai_service.llm.quota"):
        for _ in range(3):
            guard.reserve(request_for(run), Decimal("0.01"))
    [record] = [r for r in caplog.records if r.name == "ai_service.llm.quota"]
    assert record.levelno == logging.WARNING
    assert "0.85" not in record.getMessage() and "0.85" not in str(record.__dict__)
    assert str(run.user_id) not in record.getMessage()


# --- Settings --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AI_QUOTA_DAILY_USD", "0"),
        ("AI_QUOTA_DAILY_USD", "-1"),
        ("AI_QUOTA_MONTHLY_USD", "nan"),
        ("AI_QUOTA_MONTHLY_USD", "inf"),
        ("AI_QUOTA_HARD_CAP_FACTOR", "0.5"),
        ("AI_QUOTA_DAILY_USD", "20"),  # a day above the default month
    ],
)
def test_t211_bad_quota_settings_stop_the_startup(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_t211_defaults_are_set() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.quota_daily_usd == Decimal("0.20")
    assert settings.quota_monthly_usd == Decimal("2.00")
    assert settings.quota_hard_cap_factor == Decimal(3)
