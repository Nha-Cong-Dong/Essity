from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.learning_day import day_bounds, learning_day

HCM = ZoneInfo("Asia/Ho_Chi_Minh")  # UTC+7, no DST
BERLIN = ZoneInfo("Europe/Berlin")  # DST: 02:00 -> 03:00 in March, 03:00 -> 02:00 in October
HAVANA = ZoneInfo("America/Havana")  # DST starts at midnight: 00:00 does not exist that day


def local(tz: ZoneInfo, *args: int) -> datetime:
    return datetime(*args, tzinfo=tz)  # pyright: ignore[reportArgumentType]


def test_before_day_start_belongs_to_previous_day() -> None:
    assert learning_day(local(HCM, 2026, 10, 16, 3, 59, 59), HCM, 4) == date(2026, 10, 15)


def test_at_day_start_belongs_to_new_day() -> None:
    assert learning_day(local(HCM, 2026, 10, 16, 4, 0), HCM, 4) == date(2026, 10, 16)


def test_midnight_still_belongs_to_previous_day() -> None:
    assert learning_day(local(HCM, 2026, 10, 16, 0, 0), HCM, 4) == date(2026, 10, 15)


def test_day_start_hour_zero_is_the_calendar_day() -> None:
    assert learning_day(local(HCM, 2026, 10, 16, 0, 0), HCM, 0) == date(2026, 10, 16)


def test_uses_local_time_not_utc() -> None:
    # 22:00 UTC on the 15th is 05:00 on the 16th in Ho Chi Minh City.
    assert learning_day(datetime(2026, 10, 15, 22, 0, tzinfo=UTC), HCM, 4) == date(2026, 10, 16)


def test_bounds_in_zone_without_dst() -> None:
    start, end = day_bounds(date(2026, 10, 16), HCM, 4)
    assert start == datetime(2026, 10, 15, 21, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 16, 21, 0, tzinfo=UTC)


def test_day_is_23_hours_when_dst_starts() -> None:
    # The 02:00 jump on 29 March happens before 04:00, so it shortens the learning day of the 28th.
    start, end = day_bounds(date(2026, 3, 28), BERLIN, 4)
    assert end - start == timedelta(hours=23)


def test_day_is_25_hours_when_dst_ends() -> None:
    start, end = day_bounds(date(2026, 10, 24), BERLIN, 4)
    assert end - start == timedelta(hours=25)


def test_day_starting_inside_a_dst_gap_begins_at_the_transition() -> None:
    # Havana skips 00:00-01:00 on 2026-03-08; with day_start_hour=0 the day starts at 01:00 local.
    start, _ = day_bounds(date(2026, 3, 8), HAVANA, 0)
    assert start.astimezone(HAVANA) == local(HAVANA, 2026, 3, 8, 1, 0)
    assert learning_day(start - timedelta(seconds=1), HAVANA, 0) == date(2026, 3, 7)


def test_naive_instant_is_rejected() -> None:
    with pytest.raises(ValueError):
        learning_day(datetime(2026, 10, 16, 4, 0), HCM, 4)


@pytest.mark.parametrize("hour", [-1, 24])
def test_hour_out_of_range_is_rejected(hour: int) -> None:
    with pytest.raises(ValueError):
        learning_day(datetime(2026, 10, 16, tzinfo=UTC), HCM, hour)


instants = st.datetimes(
    min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1), timezones=st.just(UTC)
)


@given(instant=instants, tz=st.timezones(), hour=st.integers(0, 23))
def test_instant_falls_inside_bounds_of_its_own_day(
    instant: datetime, tz: ZoneInfo, hour: int
) -> None:
    day = learning_day(instant, tz, hour)
    start, end = day_bounds(day, tz, hour)
    assert start <= instant < end


@given(
    day=st.dates(date(2000, 1, 1), date(2099, 12, 31)), tz=st.timezones(), hour=st.integers(0, 23)
)
def test_bounds_are_the_exact_edges_of_the_day(day: date, tz: ZoneInfo, hour: int) -> None:
    start, end = day_bounds(day, tz, hour)
    tick = timedelta(microseconds=1)
    assert learning_day(start, tz, hour) == day
    assert learning_day(end - tick, tz, hour) == day
    assert learning_day(start - tick, tz, hour) == day - timedelta(days=1)
    assert learning_day(end, tz, hour) == day + timedelta(days=1)
