"""Rules of a study session that need no database (US-02, T4.12)."""

import datetime

# How far back a session may be logged: "ghi bù" for a day studied up to a year ago (Q14).
LATE_LOG_DAYS = 366

# POST /sessions answers within this, reading files and calling ai-service together. The chain
# shrinks downstream: web 6 s > core-api 5 s > ai-service 4 s (CONVENTIONS "Timeout").
CREATE_BUDGET_SECONDS = 4.5
AI_TIMEOUT_SECONDS = 5.0
# Less than this left is not worth a call: the learner gets the manual form at once.
MIN_AI_SECONDS = 0.5


def ai_timeout(remaining: float) -> float | None:
    """Seconds ai-service may take, or None when too little time is left to ask."""
    return None if remaining < MIN_AI_SECONDS else min(AI_TIMEOUT_SECONDS, remaining)


def page_range_ok(first: int, last: int, page_count: int) -> bool:
    """FILE pages, 1-based: `1 <= first <= last <= page_count`."""
    return 1 <= first <= last <= page_count


def studied_on_ok(studied_on: datetime.date, today: datetime.date) -> bool:
    """A real study day: not in the future, not more than `LATE_LOG_DAYS` back."""
    return today - datetime.timedelta(days=LATE_LOG_DAYS) <= studied_on <= today
