"""The per-user cost quota, asked before every LLM call (T2.11, ADR-0010).

Windows are the UTC day and the UTC month, taken from the database clock. Spent money is the sum
of `llm_call.cost_usd` of the user in the window; money set aside for calls in flight is in
`llm_reservation`. A call is admitted when `spent + reserved + estimate <= limit` for both
windows, and the reservation is written in the same transaction as the check, under a per-user
advisory lock held for a few milliseconds (not for the call). So two requests at once cannot
both see "nothing spent".

Limits: a task in `hard_cap_tasks` (grading) is held to `limit x hard_cap_factor` and is refused
there (`hard=True`); any other task (indexing a document) is held to the plain limit and is
deferred (`hard=False`). A new task needs no change here. Messages carry no amounts: an error
about one account never says anything about the money of another.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

from sqlalchemy import delete, text, update
from sqlalchemy.orm import Session

from ai_service.db.models import LlmReservation
from ai_service.db.session import SessionFactory
from ai_service.llm.pricing import Price, cost_usd
from ai_service.llm.types import LlmRequest

_log = logging.getLogger(__name__)

Window = Literal["day", "month"]
WARN_RATIO = Decimal("0.8")
# Output tokens assumed when the adapter states no `max_tokens`.
DEFAULT_MAX_OUTPUT_TOKENS = 8192
# Worst case of one image (<= 1400 px long side is about 2600 tokens; rounded up).
IMAGE_TOKENS = 2700
# An admitted call that never settles (the process died) frees its reservation after this.
RESERVATION_TTL_SECONDS = 120
LOCK_TIMEOUT = "2s"
# First key of the advisory lock, so this lock cannot collide with another feature's.
_LOCK_NAMESPACE = 2011
_WARNED_LIMIT = 10_000


class QuotaExceededError(Exception):
    """The call would pass the quota. `hard`: the hard cap (refuse); otherwise wait (defer)."""

    def __init__(self, *, hard: bool, window: Window) -> None:
        super().__init__("ai quota exceeded")
        self.hard = hard
        self.window = window


class QuotaUnavailableError(Exception):
    """The spend could not be read: fail closed, no call is made."""


@dataclass(frozen=True)
class QuotaLimits:
    daily: Decimal
    monthly: Decimal
    hard_cap_factor: Decimal


def estimate_cost(price: Price, request: LlmRequest, params: dict[str, object]) -> Decimal:
    """Worst case of a call: the whole prompt as tokens (one character is at most one token)
    and `max_tokens` of output."""
    chars = len(request.system) + len(request.user) + len(json.dumps(request.output_schema))
    max_output = params.get("max_tokens", DEFAULT_MAX_OUTPUT_TOKENS)
    assert isinstance(max_output, int)
    return cost_usd(
        price, input_tokens=chars + IMAGE_TOKENS * len(request.images), output_tokens=max_output
    )


class QuotaGuard(Protocol):
    def reserve(self, request: LlmRequest, estimate: Decimal) -> uuid.UUID | None:
        """Admit the call and set `estimate` aside, or raise."""
        ...

    def release(self, reservation_id: uuid.UUID, session: Session | None = None) -> None:
        """Give the reservation back: inside `session` (not committed) or in a transaction."""
        ...

    def hold(self, reservation_id: uuid.UUID) -> None:
        """Keep the reservation to the end of the month: the spend could not be recorded."""
        ...


_CLOCK = text(
    """
    SELECT date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS day_start,
           date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS month_start
    """
)
_SPENT = text(
    """
    SELECT COALESCE(SUM(cost_usd) FILTER (WHERE created_at >= :day_start), 0) AS day_spent,
           COALESCE(SUM(cost_usd), 0) AS month_spent
    FROM llm_call WHERE user_id = :user_id AND created_at >= :month_start
    """
)
_RESERVED = text(
    "SELECT COALESCE(SUM(amount_usd), 0) FROM llm_reservation "
    "WHERE user_id = :user_id AND expires_at > now()"
)
_MONTH_END = text(
    "SELECT (date_trunc('month', now() AT TIME ZONE 'UTC') + interval '1 month') AT TIME ZONE 'UTC'"
)


class DbQuotaGuard:
    def __init__(
        self,
        sessions: SessionFactory,
        limits: QuotaLimits,
        *,
        hard_cap_tasks: frozenset[str] = frozenset({"grade"}),
    ) -> None:
        self._sessions = sessions
        self._limits = limits
        self._hard_cap_tasks = hard_cap_tasks
        self._warned: set[tuple[uuid.UUID, Window, datetime]] = set()

    def reserve(self, request: LlmRequest, estimate: Decimal) -> uuid.UUID | None:
        hard_task = request.task in self._hard_cap_tasks
        factor = self._limits.hard_cap_factor if hard_task else Decimal(1)
        user = request.user_id  # from the authenticated request, never from the payload
        try:
            with self._sessions() as session, session.begin():
                # Before the lock: the timeout then covers the wait for it.
                session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:ns, hashtext(:user_id))"),
                    {"ns": _LOCK_NAMESPACE, "user_id": str(user)},
                )
                clock = session.execute(_CLOCK).one()
                spent = session.execute(
                    _SPENT,
                    {
                        "user_id": user,
                        "day_start": clock.day_start,
                        "month_start": clock.month_start,
                    },
                ).one()
                session.execute(
                    delete(LlmReservation).where(
                        LlmReservation.user_id == user, LlmReservation.expires_at <= text("now()")
                    )
                )
                reserved = Decimal(session.execute(_RESERVED, {"user_id": user}).scalar_one())
                windows: list[tuple[Window, Decimal, Decimal, datetime]] = [
                    ("day", spent.day_spent, self._limits.daily, clock.day_start),
                    ("month", spent.month_spent, self._limits.monthly, clock.month_start),
                ]
                for window, window_spent, limit, start in windows:
                    self._warn_if_near(user, window, start, window_spent, limit)
                    if window_spent + reserved + estimate > limit * factor:
                        raise QuotaExceededError(hard=hard_task, window=window)
                reservation = LlmReservation(
                    user_id=user,
                    amount_usd=estimate,
                    expires_at=text(f"now() + interval '{RESERVATION_TTL_SECONDS} seconds'"),
                )
                session.add(reservation)
                session.flush()
                return reservation.id
        except QuotaExceededError:
            raise
        except Exception as error:
            _log.exception("quota check failed")
            raise QuotaUnavailableError from error

    def release(self, reservation_id: uuid.UUID, session: Session | None = None) -> None:
        statement = delete(LlmReservation).where(LlmReservation.id == reservation_id)
        if session is not None:
            session.execute(statement)
            return
        try:
            with self._sessions() as own, own.begin():
                own.execute(statement)
        except Exception:
            _log.exception("quota reservation not released")  # it expires by itself

    def hold(self, reservation_id: uuid.UUID) -> None:
        try:
            with self._sessions() as session, session.begin():
                month_end = session.execute(_MONTH_END).scalar_one()
                session.execute(
                    update(LlmReservation)
                    .where(LlmReservation.id == reservation_id)
                    .values(expires_at=month_end)
                )
        except Exception:
            _log.exception("quota reservation not held")

    def _warn_if_near(
        self, user: uuid.UUID, window: Window, start: datetime, spent: Decimal, limit: Decimal
    ) -> None:
        key = (user, window, start)
        if spent < limit * WARN_RATIO or key in self._warned:
            return
        if len(self._warned) >= _WARNED_LIMIT:
            self._warned.clear()
        self._warned.add(key)
        # No amounts, no user: the log line is read by more people than the account is.
        _log.warning("ai quota near limit", extra={"window": window})
