"""How long a session lives (ADR-0014, ADR-0020 §1).

A session ends 30 days after it was last used, and in any case 90 days after sign-in: a stolen
token used every day still dies. Pure functions; the clock is the caller's.
"""

from datetime import datetime, timedelta

SESSION_IDLE = timedelta(days=30)  # sliding: every request pushes the end back
SESSION_MAX = timedelta(days=90)  # absolute, from sign-in


def session_expiry(created_at: datetime, now: datetime) -> datetime:
    """When a session used at `now` ends, if it is not used again."""
    return min(now + SESSION_IDLE, created_at + SESSION_MAX)


def session_is_active(
    created_at: datetime, expires_at: datetime, revoked_at: datetime | None, now: datetime
) -> bool:
    return revoked_at is None and now < expires_at and now < created_at + SESSION_MAX
