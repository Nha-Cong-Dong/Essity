"""T1.20 plan K3: "còn N ngày" comes from core-api, counted in the user's learning days.

One rule for "today" (US-01 AC2's), so web and API never disagree around 04:00.
"""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_subjects_api import create, in_days

from accounts import signed_in
from core_api.domain.subjects import days_until_exam

HCM = ZoneInfo("Asia/Ho_Chi_Minh")


def at(local: str) -> datetime:
    return datetime.fromisoformat(local).replace(tzinfo=HCM)


def test_k3_an_exam_tomorrow_is_one_day_away() -> None:
    assert days_until_exam(date(2026, 10, 23), at("2026-10-22T20:00"), HCM, 4) == 1


def test_k3_at_0359_the_learning_day_is_still_yesterday() -> None:
    # 03:59 on the 23rd belongs to the 22nd: an exam on the 23rd is still one day away.
    assert days_until_exam(date(2026, 10, 23), at("2026-10-23T03:59"), HCM, 4) == 1


def test_k3_at_0400_a_new_learning_day_begins() -> None:
    assert days_until_exam(date(2026, 10, 23), at("2026-10-23T04:00"), HCM, 4) == 0


def test_k3_across_a_month_end() -> None:
    assert days_until_exam(date(2026, 12, 15), at("2026-10-31T23:00"), HCM, 4) == 45


def test_k3_an_exam_that_is_over_counts_below_zero() -> None:
    assert days_until_exam(date(2026, 10, 20), at("2026-10-22T20:00"), HCM, 4) == -2


def _days(body: Any) -> int:
    return body["days_until_exam"]


def test_k3_post_get_and_patch_say_how_many_days_are_left(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    created = create(client, headers, "Mạng máy tính", in_days(user, 55))
    assert _days(created.json()) == 55

    listed = client.get("/v1/subjects", headers=headers).json()
    assert [_days(s) for s in listed] == [55]

    changed = client.patch(
        f"/v1/subjects/{created.json()['id']}",
        json={"exam_date": in_days(user, 7)},
        headers=headers,
    )
    assert _days(changed.json()) == 7
