"""T1.19: rules for a subject's name and exam date, without a database (US-01 AC2; B11, B12)."""

import unicodedata
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.learning_day import learning_day
from core_api.domain.subjects import (
    MAX_DAYS_AHEAD,
    ExamDateNotInFutureError,
    ExamDateTooFarError,
    normalize_subject_name,
    validate_exam_date,
)

HCM = ZoneInfo("Asia/Ho_Chi_Minh")


def at(local: str, tz: ZoneInfo = HCM) -> datetime:
    return datetime.fromisoformat(local).replace(tzinfo=tz)


def test_ac2_tomorrow_is_accepted() -> None:
    validate_exam_date(date(2026, 10, 22), at("2026-10-21T20:00"), HCM, 4)


def test_ac2_today_is_refused() -> None:
    with pytest.raises(ExamDateNotInFutureError):
        validate_exam_date(date(2026, 10, 21), at("2026-10-21T20:00"), HCM, 4)


def test_ac2_the_past_is_refused() -> None:
    with pytest.raises(ExamDateNotInFutureError):
        validate_exam_date(date(2025, 6, 1), at("2026-10-21T20:00"), HCM, 4)


def test_ac2_at_0359_the_learning_day_is_still_yesterday() -> None:
    # 03:59 on the 22nd is the learning day of the 21st: an exam on the 22nd is still ahead.
    validate_exam_date(date(2026, 10, 22), at("2026-10-22T03:59"), HCM, 4)


def test_ac2_at_0400_a_new_learning_day_starts() -> None:
    with pytest.raises(ExamDateNotInFutureError):
        validate_exam_date(date(2026, 10, 22), at("2026-10-22T04:00"), HCM, 4)


def test_ac2_uses_the_users_time_zone_and_day_start() -> None:
    now = datetime(2026, 10, 21, 22, 0, tzinfo=UTC)  # 05:00 on the 22nd in Ho Chi Minh City
    with pytest.raises(ExamDateNotInFutureError):
        validate_exam_date(date(2026, 10, 22), now, HCM, 4)
    validate_exam_date(date(2026, 10, 22), now, ZoneInfo("UTC"), 4)
    # The same instant with a day starting at 06:00 is still the 21st in Ho Chi Minh City.
    validate_exam_date(date(2026, 10, 22), now, HCM, 6)


def test_k17_two_years_ahead_is_the_last_accepted_day() -> None:
    now = at("2026-10-21T20:00")
    assert MAX_DAYS_AHEAD == 730
    validate_exam_date(date(2026, 10, 21) + timedelta(days=730), now, HCM, 4)
    with pytest.raises(ExamDateTooFarError):
        validate_exam_date(date(2026, 10, 21) + timedelta(days=731), now, HCM, 4)


def test_k17_a_mistyped_year_is_refused() -> None:
    with pytest.raises(ExamDateTooFarError):
        validate_exam_date(date(2062, 12, 15), at("2026-10-21T20:00"), HCM, 4)


def test_k17_the_cap_counts_from_the_learning_day() -> None:
    # 03:59 on the 22nd is still the 21st's learning day: day 730 counts from the 21st.
    now = at("2026-10-22T03:59")
    validate_exam_date(date(2026, 10, 21) + timedelta(days=730), now, HCM, 4)
    with pytest.raises(ExamDateTooFarError):
        validate_exam_date(date(2026, 10, 21) + timedelta(days=731), now, HCM, 4)


@given(
    instant=st.datetimes(
        min_value=datetime(2020, 1, 1), max_value=datetime(2040, 1, 1), timezones=st.just(UTC)
    ),
    hour=st.integers(min_value=0, max_value=23),
)
def test_ac2_exactly_the_day_after_the_learning_day_is_the_first_accepted(
    instant: datetime, hour: int
) -> None:
    today = learning_day(instant, HCM, hour)
    validate_exam_date(today + timedelta(days=1), instant, HCM, hour)
    with pytest.raises(ExamDateNotInFutureError):
        validate_exam_date(today, instant, HCM, hour)


def test_b12_name_is_stripped() -> None:
    assert normalize_subject_name("  Mạng máy tính \n") == "Mạng máy tính"


def test_b12_decomposed_vietnamese_becomes_composed() -> None:
    decomposed = unicodedata.normalize("NFD", "Mạng máy tính")
    assert decomposed != "Mạng máy tính"
    assert normalize_subject_name(decomposed) == "Mạng máy tính"
