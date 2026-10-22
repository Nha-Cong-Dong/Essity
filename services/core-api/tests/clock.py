"""The fixed "now" of the subjects tests (R23): a run that crosses 04:00 in Ho Chi Minh City
(21:00 UTC) cannot see two different learning days between the test and the server."""

from datetime import UTC, date, datetime, timedelta

# 03:30 on 23 October in Ho Chi Minh City: before the 04:00 day start, so the learning day is the
# 22nd there and the 22nd in UTC as well.
FROZEN_NOW = datetime(2026, 10, 22, 20, 30, tzinfo=UTC)


def future_exam(days: int = 60) -> date:
    """An exam date for tests that write through a repository, which checks no dates (R25)."""
    return date.today() + timedelta(days=days)
