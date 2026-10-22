"""Rules for a subject (US-01): its name, and an exam date that is still ahead but not too far."""

import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import learning_day

# Plan K17: two years from today is the latest exam date. A year typed wrong (2062 for 2026)
# would otherwise pass and leave the exam constraint (T2.5) with nothing to pull towards.
MAX_DAYS_AHEAD = 730


class ExamDateNotInFutureError(ValueError):
    """The exam date is today or earlier, in the user's learning days (AC2, DESIGN §6.8)."""


class ExamDateTooFarError(ValueError):
    """The exam date is more than MAX_DAYS_AHEAD learning days away (plan K17)."""


def validate_exam_date(exam_date: date, now: datetime, tz: ZoneInfo, day_start_hour: int) -> None:
    """Accept only a date after the user's current learning day and at most MAX_DAYS_AHEAD
    later: an exam today is refused, and at 03:59 with a day starting at 04:00 "today" is still
    yesterday."""
    today = learning_day(now, tz, day_start_hour)
    if exam_date <= today:
        raise ExamDateNotInFutureError(exam_date)
    if exam_date > today + timedelta(days=MAX_DAYS_AHEAD):
        raise ExamDateTooFarError(exam_date)


def days_until_exam(exam_date: date, now: datetime, tz: ZoneInfo, day_start_hour: int) -> int:
    """Learning days from today to the exam: 1 for tomorrow, 0 on the day, below 0 once it is
    over. The same "today" as validate_exam_date, so the screen and the API agree at 04:00."""
    return (exam_date - learning_day(now, tz, day_start_hour)).days


def normalize_subject_name(name: str) -> str:
    """Stripped and composed (NFC): Vietnamese typed as combining marks (Unikey's "Unicode tổ
    hợp") is stored the same as precomposed text."""
    return unicodedata.normalize("NFC", name).strip()
