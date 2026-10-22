"""Rules for a subject (US-01): its name, and an exam date that is still ahead."""

import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import learning_day


class ExamDateNotInFutureError(ValueError):
    """The exam date is today or earlier, in the user's learning days (AC2, DESIGN §6.8)."""


def validate_exam_date(exam_date: date, now: datetime, tz: ZoneInfo, day_start_hour: int) -> None:
    """Accept only a date after the user's current learning day: an exam today is refused,
    and at 03:59 with a day starting at 04:00 "today" is still yesterday."""
    if exam_date <= learning_day(now, tz, day_start_hour):
        raise ExamDateNotInFutureError(exam_date)


def normalize_subject_name(name: str) -> str:
    """Stripped and composed (NFC): Vietnamese typed as combining marks (Unikey's "Unicode tổ
    hợp") is stored the same as precomposed text."""
    return unicodedata.normalize("NFC", name).strip()
