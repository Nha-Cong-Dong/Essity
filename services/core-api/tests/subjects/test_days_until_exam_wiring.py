"""T1.20 plan K3, tester: the endpoints feed `days_until_exam` the *user's* zone and day start.

The domain function is tested on its own; this pins the wiring in `_out` with a frozen clock and
users whose zone and day start differ, so the answer does not depend on the hour the suite runs.
Breaks if `_out` hardcodes a zone or hour, or counts from the UTC date instead of the learning day.
"""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.repositories.subject import SubjectRepository

# 2026-10-22 20:30 UTC = 03:30 on the 23rd in Ho Chi Minh City, 09:30 on the 23rd in Auckland,
# 13:30 on the 22nd in Los Angeles.
FROZEN = datetime(2026, 10, 22, 20, 30, tzinfo=UTC)


class _Clock(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> "_Clock":  # type: ignore[override]
        return cls.fromtimestamp(FROZEN.timestamp(), tz)


def _days_for(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    *,
    timezone: str,
    day_start_hour: int,
    exam: date,
) -> int:
    monkeypatch.setattr("core_api.api.subjects.datetime", _Clock)
    user, headers = signed_in(db_session)
    user.timezone = timezone
    user.day_start_hour = day_start_hour
    SubjectRepository(db_session, user.id).create_with_exam("Mạng máy tính", exam)
    db_session.flush()
    listed = client.get("/v1/subjects", headers=headers).json()
    return listed[0]["days_until_exam"]


@pytest.mark.parametrize(
    ("timezone", "day_start_hour", "expected"),
    [
        ("Asia/Ho_Chi_Minh", 4, 1),  # 03:30 on the 23rd is still the 22nd's learning day
        ("Asia/Ho_Chi_Minh", 0, 0),  # a day starting at midnight: it is already the 23rd
        ("Pacific/Auckland", 0, 0),  # 09:30 on the 23rd
        ("America/Los_Angeles", 4, 1),  # 13:30 on the 22nd
    ],
)
def test_k3_the_list_counts_in_the_users_own_learning_day(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    timezone: str,
    day_start_hour: int,
    expected: int,
) -> None:
    days = _days_for(
        client,
        db_session,
        monkeypatch,
        timezone=timezone,
        day_start_hour=day_start_hour,
        exam=date(2026, 10, 23),
    )
    assert days == expected
