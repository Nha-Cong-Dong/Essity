"""The fixed "now" of the subjects tests (R23): a run that crosses 04:00 in Ho Chi Minh City
(21:00 UTC) cannot see two different learning days between the test and the server."""

from datetime import UTC, date, datetime, timedelta
from itertools import count

# 03:30 on 23 October in Ho Chi Minh City: before the 04:00 day start, so the learning day is the
# 22nd there and the 22nd in UTC as well.
FROZEN_NOW = datetime(2026, 10, 22, 20, 30, tzinfo=UTC)


def future_exam(days: int = 60) -> date:
    """An exam date for tests that write through a repository, which checks no dates (R25).
    From FROZEN_NOW, like the routes, so a test that mixes the two agrees with itself."""
    return FROZEN_NOW.date() + timedelta(days=days)


_spare = count(1)


def spare_day() -> date:
    """A learning day no other test session uses: only one session may be open per learning day
    (T2.9 plan C4), so a test that opens another one beside its fixture's takes a day of its own."""
    return date(2030, 1, 1) + timedelta(days=next(_spare))
