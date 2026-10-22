"""R23 for PATCH /v1/subjects/{id}: test_r23_clock.py covers POST and GET, and a PATCH that went
back to `datetime.now` stayed green. Written by the Tester (feature-tester, 23/10)."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in

# The user is in Ho Chi Minh City (UTC+7), day starting at 04:00.
AT_0359 = datetime(2026, 10, 22, 20, 59, tzinfo=UTC)  # 23 Oct 03:59 local: learning day 22 Oct
AT_0400 = datetime(2026, 10, 22, 21, 0, tzinfo=UTC)  # 23 Oct 04:00 local: learning day 23 Oct


def create(client: TestClient, headers: dict[str, str], exam_date: str) -> str:
    response = client.post(
        "/v1/subjects", json={"name": "Mạng máy tính", "exam_date": exam_date}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.parametrize(
    ("instant", "new_date", "status"),
    [
        (AT_0359, "2026-10-23", 200),  # tomorrow at 03:59
        (AT_0400, "2026-10-23", 422),  # today at 04:00: refused
        (AT_0359, "2028-10-21", 200),  # 22 Oct + 730
        (AT_0359, "2028-10-22", 422),  # 22 Oct + 731
        (AT_0400, "2028-10-22", 200),  # 23 Oct + 730
    ],
)
def test_r23_patch_uses_the_injected_clock(
    client: TestClient,
    db_session: Session,
    set_now: Callable[[datetime], None],
    instant: datetime,
    new_date: str,
    status: int,
) -> None:
    # Red when: change_subject calls datetime.now itself instead of taking get_now (the exam-date
    # check then follows the hour the suite runs at, not the instant the test sets).
    _, headers = signed_in(db_session)
    set_now(datetime(2026, 10, 1, 5, 0, tzinfo=UTC))
    subject = create(client, headers, "2026-12-15")
    set_now(instant)
    response = client.patch(
        f"/v1/subjects/{subject}", json={"exam_date": new_date}, headers=headers
    )
    assert response.status_code == status


def test_r23_patch_answers_days_until_exam_from_the_injected_clock(
    client: TestClient, db_session: Session, set_now: Callable[[datetime], None]
) -> None:
    # Red when: the PATCH answer's days_until_exam is computed from the real clock: years away
    # from 2030, it would be hundreds of days off, or negative.
    _, headers = signed_in(db_session)
    set_now(datetime(2030, 1, 1, 12, 0, tzinfo=UTC))
    subject = create(client, headers, "2030-03-01")
    set_now(datetime(2030, 1, 10, 12, 0, tzinfo=UTC))
    response = client.patch(f"/v1/subjects/{subject}", json={"name": "Đổi tên"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["days_until_exam"] == 50  # 10 Jan -> 1 Mar 2030
