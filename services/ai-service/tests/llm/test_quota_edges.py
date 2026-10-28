"""T2.11, tester: edges of the cost quota the first tests left open.

The exact limit (Q2 `<=`), a lock held by another process (fail closed, not hang), failures that
may have been billed, and the app reading AI_QUOTA_* at startup (real guard, fake provider).
"""

import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from ai_service.config import get_settings
from ai_service.llm.pricing import price_for
from ai_service.llm.quota import (
    QuotaExceededError,
    QuotaLimits,
    QuotaUnavailableError,
    estimate_cost,
)
from ai_service.llm.types import ProviderError
from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from tests.grade.helpers import grade_body
from tests.llm.helpers import make_request
from tests.llm.test_quota import (
    MODEL,
    Scripted,
    client_for,
    deadline,
    guard_for,
    new_run,
    request_for,
    reservations_of,
    spend,
    today_start,
)

HEADERS = {SERVICE_TOKEN_HEADER: "test-service-token-0123456789abcdef"}


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def test_t211_a_call_landing_exactly_on_the_limit_is_admitted(
    sessions: sessionmaker[Session],
) -> None:
    # Red when: the check is `>=` instead of `>`: a user with exactly enough left is refused
    # (Q2: admitted while spent + reserved + estimate <= limit).
    run = new_run(sessions)
    spend(sessions, run, "0.99")
    guard = guard_for(sessions, hard_cap_tasks=frozenset())
    guard.reserve(request_for(run), Decimal("0.01"))  # 0.99 + 0.01 == 1.00
    with pytest.raises(QuotaExceededError):
        guard.reserve(request_for(run), Decimal("0.000001"))  # one micro-dollar over


def test_t211_a_long_prompt_is_counted_in_the_estimate_at_the_long_price() -> None:
    # Red when: the estimate counts only `max_tokens` of output and not the prompt: a 200k
    # character answer (each character up to a token, long-prompt price 0.50/M) is under-reserved
    # by some 200 times, and a few of them at once pass the cap.
    request = make_request(user="đ" * 200_000)
    estimate = estimate_cost(price_for(MODEL), request, {"max_tokens": 1000})
    assert estimate >= Decimal("0.100000") + Decimal("0.0025")  # 200k x 0.50/M + 1k x 2.50/M


def test_t211_a_lock_held_elsewhere_fails_closed_instead_of_hanging(
    engine: Engine, sessions: sessionmaker[Session]
) -> None:
    # Red when: `SET LOCAL lock_timeout` is dropped or comes after the lock: a stuck holder of
    # the user's lock hangs every request of that user instead of failing closed (503).
    run = new_run(sessions)
    guard = guard_for(sessions)
    outcome: list[BaseException | None] = []

    def reserve() -> None:
        try:
            guard.reserve(request_for(run), Decimal("0.01"))
            outcome.append(None)
        except BaseException as error:  # noqa: BLE001  # the outcome is what the test checks
            outcome.append(error)

    with engine.connect() as holder:
        holder.execute(text("SELECT pg_advisory_lock(2011, hashtext(:u))"), {"u": str(run.user_id)})
        worker = threading.Thread(target=reserve, daemon=True)
        started = time.monotonic()
        worker.start()
        worker.join(timeout=15)
        waited = time.monotonic() - started
        holder.execute(
            text("SELECT pg_advisory_unlock(2011, hashtext(:u))"), {"u": str(run.user_id)}
        )
        holder.commit()
    worker.join(timeout=15)
    assert waited < 15, "reserve waited for the lock with no timeout"
    assert len(outcome) == 1 and isinstance(outcome[0], QuotaUnavailableError)


@pytest.mark.parametrize("failure", [ProviderError("connection_error"), RuntimeError("bug")])
def test_t211_failures_that_may_have_been_billed_keep_the_reservation(
    engine: Engine, sessions: sessionmaker[Session], failure: Exception
) -> None:
    # Red when: a connection error after the request went out, or an unexpected error in the
    # adapter, frees the reservation: the provider may have charged and nothing counts it.
    run = new_run(sessions)
    guard = guard_for(sessions, QuotaLimits(Decimal("1.00"), Decimal("10.00"), Decimal(1)))
    adapter = Scripted(failure, max_tokens=1_200_000)  # 0.60 each
    client = client_for(adapter, sessions, guard)
    with pytest.raises(Exception):  # noqa: B017, PT011  # the failure itself is not the subject
        client.call(request_for(run), deadline=deadline())
    [held] = reservations_of(engine, run)
    assert held.expires_at > datetime.now(UTC) + timedelta(hours=1)
    with pytest.raises(QuotaExceededError):
        client.call(request_for(run), deadline=deadline())
    assert adapter.calls == 1


# --- The app reads AI_QUOTA_* at startup (lifespan, real guard, fake provider) ----------------


@pytest.fixture
def app_with_quota(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AI_QUOTA_DAILY_USD", "0.01")
    monkeypatch.setenv("AI_QUOTA_MONTHLY_USD", "1.00")
    yield


def post_grade(sessions: sessionmaker[Session], user_spent: tuple[str, datetime | None]) -> int:
    run = new_run(sessions)
    spend(sessions, run, user_spent[0], user_spent[1])
    body = grade_body(user_id=str(run.user_id))
    get_settings.cache_clear()  # the env may have changed within the test
    with TestClient(create_app(), headers=HEADERS) as client:
        response = client.post("/v1/grade", json=body)
    if response.status_code == 429:
        assert response.json() == {"code": "quota_hard_cap"}
    return response.status_code


@pytest.mark.usefixtures("app_with_quota")
def test_t211_app_grades_up_to_the_daily_hard_cap_from_settings(
    sessions: sessionmaker[Session],
) -> None:
    # Red when: main.py builds the guard without AI_QUOTA_DAILY_USD or without the hard-cap
    # factor (daily 0.01 x 3 = 0.03): 0.025 spent must still grade, 0.05 must stop.
    assert post_grade(sessions, ("0.025", None)) == 200
    assert post_grade(sessions, ("0.05", None)) == 429


@pytest.mark.usefixtures("app_with_quota")
def test_t211_app_reads_the_hard_cap_factor(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: AI_QUOTA_HARD_CAP_FACTOR is ignored (0.01 x 10 = 0.10 > 0.05 spent).
    monkeypatch.setenv("AI_QUOTA_HARD_CAP_FACTOR", "10")
    assert post_grade(sessions, ("0.05", None)) == 200
    monkeypatch.setenv("AI_QUOTA_HARD_CAP_FACTOR", "2")
    assert post_grade(sessions, ("0.025", None)) == 429  # 0.02 cap


@pytest.mark.usefixtures("app_with_quota")
def test_t211_app_reads_the_monthly_limit(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: main.py builds the guard without AI_QUOTA_MONTHLY_USD: money spent earlier in
    # the month (not today) never stops grading.
    if datetime.now(UTC).day == 1:
        pytest.skip("yesterday is not in this month")
    monkeypatch.setenv("AI_QUOTA_MONTHLY_USD", "0.01")
    yesterday = today_start() - timedelta(seconds=1)
    assert post_grade(sessions, ("0.05", yesterday)) == 429  # month 0.01 x 3 = 0.03
    assert post_grade(sessions, ("0.02", yesterday)) == 200
