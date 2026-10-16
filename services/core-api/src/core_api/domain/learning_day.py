"""The "learning day": a calendar day that starts at `day_start_hour` local time, not midnight.

A review at 01:30 still belongs to yesterday when the day starts at 04:00 (ADR-0009, Q12).
py-fsrs only works in UTC, so every "due today" query goes through these functions.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def learning_day(instant: datetime, tz: ZoneInfo, day_start_hour: int) -> date:
    _check_hour(day_start_hour)
    if instant.tzinfo is None:
        raise ValueError("instant must be timezone-aware")
    local = instant.astimezone(tz)
    if local.hour < day_start_hour:
        return local.date() - timedelta(days=1)
    return local.date()


def day_bounds(day: date, tz: ZoneInfo, day_start_hour: int) -> tuple[datetime, datetime]:
    """UTC instants [start, end) of a learning day. Not always 24 hours long because of DST."""
    _check_hour(day_start_hour)
    return (
        _day_start(day, tz, day_start_hour),
        _day_start(day + timedelta(days=1), tz, day_start_hour),
    )


def _day_start(day: date, tz: ZoneInfo, day_start_hour: int) -> datetime:
    wall = datetime.combine(day, time(day_start_hour), tzinfo=tz)
    # fold=0 picks the first occurrence when the wall time repeats (DST ends).
    after = wall.astimezone(UTC)
    if after.astimezone(tz).replace(tzinfo=None) == wall.replace(tzinfo=None):
        return after
    # The wall time does not exist (DST starts): the day begins at the transition itself.
    # fold=1 reads the wall time with the post-transition offset, which lands before it.
    # Transitions fall on whole seconds, so search between the two readings in seconds.
    lo = int(wall.replace(fold=1).astimezone(UTC).timestamp())
    hi = int(after.timestamp())
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if learning_day(datetime.fromtimestamp(mid, UTC), tz, day_start_hour) == day:
            hi = mid
        else:
            lo = mid
    return datetime.fromtimestamp(hi, UTC)


def _check_hour(day_start_hour: int) -> None:
    if not 0 <= day_start_hour <= 23:
        raise ValueError("day_start_hour must be between 0 and 23")
