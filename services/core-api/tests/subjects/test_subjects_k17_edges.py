"""K17 (two-year cap): edges the first tests did not pin, found by breaking the code on purpose.

Each test names the change in `src/` that turns it red.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import User
from core_api.domain.learning_day import learning_day
from core_api.domain.subjects import ExamDateTooFarError, validate_exam_date

HCM = ZoneInfo("Asia/Ho_Chi_Minh")


def in_days(user: User, days: int) -> str:
    now = datetime.now(UTC)
    today = learning_day(now, ZoneInfo(user.timezone), user.day_start_hour)
    return (today + timedelta(days=days)).isoformat()


def stored_far_subject(
    client: TestClient, db_session: Session, days: int = 1000
) -> tuple[User, dict[str, str], str]:
    """A subject whose stored date is past the cap (as if saved before the cap existed)."""
    user, headers = signed_in(db_session)
    created = client.post(
        "/v1/subjects",
        json={"name": "Mạng máy tính", "exam_date": in_days(user, 30)},
        headers=headers,
    )
    subject_id = created.json()["id"]
    db_session.execute(
        text("UPDATE exam SET exam_date = :d WHERE subject_id = :s"),
        {"d": in_days(user, days), "s": subject_id},
    )
    return user, headers, subject_id


def patch(client: TestClient, headers: dict[str, str], subject_id: str, body: object) -> Any:
    return client.patch(f"/v1/subjects/{subject_id}", json=body, headers=headers)


def test_k17_a_stored_far_date_changed_to_another_far_date_is_refused(
    client: TestClient, db_session: Session
) -> None:
    """Red if the PATCH skips the cap whenever the stored date is already past it (e.g. the
    skip becomes `found[1].exam_date > limit`), or if the check is dropped from PATCH."""
    user, headers, subject_id = stored_far_subject(client, db_session)
    response = patch(client, headers, subject_id, {"exam_date": in_days(user, 1200)})
    assert (response.status_code, response.json()) == (422, {"detail": "exam_date_too_far"})


def test_k17_a_stored_far_date_can_be_moved_to_a_near_one(
    client: TestClient, db_session: Session
) -> None:
    """Red if the cap refuses every PATCH of a subject that stored a far date: the student
    must be able to correct it."""
    user, headers, subject_id = stored_far_subject(client, db_session)
    response = patch(client, headers, subject_id, {"exam_date": in_days(user, 100)})
    assert (response.status_code, response.json()["days_until_exam"]) == (200, 100)


def test_k17_a_refused_patch_changes_neither_name_nor_date(
    client: TestClient, db_session: Session
) -> None:
    """Red if the cap is dropped from PATCH (the name would change with a refused date). Not a
    proof of check-before-write: a write before the check left a transaction open in the tester's
    run rather than turning this red."""
    user, headers = signed_in(db_session)
    created = client.post(
        "/v1/subjects",
        json={"name": "Mạng máy tính", "exam_date": in_days(user, 30)},
        headers=headers,
    ).json()
    response = patch(
        client, headers, created["id"], {"name": "Đổi tên", "exam_date": in_days(user, 731)}
    )
    assert response.status_code == 422
    (listed,) = client.get("/v1/subjects", headers=headers).json()
    assert (listed["name"], listed["exam_date"]) == ("Mạng máy tính", created["exam_date"])


def test_k17_730_days_is_counted_in_days_not_calendar_years() -> None:
    """Red if the cap becomes "two calendar years" (e.g. replace(year=+2)): from 2027-03-01 the
    730th day is 2029-02-28, because 2028 has a 29 February; 2029-03-01 is day 731."""
    now = datetime(2027, 3, 1, 12, 0, tzinfo=HCM)
    validate_exam_date(date(2029, 2, 28), now, HCM, 4)
    with pytest.raises(ExamDateTooFarError):
        validate_exam_date(date(2029, 3, 1), now, HCM, 4)


def test_k17_the_cap_follows_the_day_start_of_the_user() -> None:
    """Red if the cap uses a fixed 04:00 or midnight instead of the user's day_start_hour: at
    05:30 with a day starting at 06:00 the learning day is still the day before."""
    now = datetime(2026, 10, 22, 5, 30, tzinfo=HCM)  # learning day: 2026-10-21 (start 06:00)
    validate_exam_date(date(2028, 10, 20), now, HCM, 6)  # 2026-10-21 + 730 days
    with pytest.raises(ExamDateTooFarError):
        validate_exam_date(date(2028, 10, 21), now, HCM, 6)
