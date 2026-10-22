"""R23: the subjects routes read the clock through `get_now`, so tests at 03:59 and 04:00 in the
user's zone are exact instead of depending on the hour the suite happens to run."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in

# The user is in Ho Chi Minh City (UTC+7), day starting at 04:00.
AT_0359 = datetime(2026, 10, 22, 20, 59, tzinfo=UTC)  # 23 Oct 03:59 local: learning day 22 Oct
AT_0400 = datetime(2026, 10, 22, 21, 0, tzinfo=UTC)  # 23 Oct 04:00 local: learning day 23 Oct


@pytest.mark.parametrize(
    ("instant", "exam_date", "status"),
    [
        (AT_0359, "2026-10-23", 201),  # tomorrow at 03:59
        (AT_0400, "2026-10-23", 422),  # today at 04:00: refused
        (AT_0359, "2028-10-21", 201),  # 22 Oct + 730
        (AT_0359, "2028-10-22", 422),  # 22 Oct + 731
        (AT_0400, "2028-10-22", 201),  # 23 Oct + 730
    ],
)
def test_r23_subjects_use_the_injected_clock(
    client: TestClient,
    db_session: Session,
    set_now: Callable[[datetime], None],
    instant: datetime,
    exam_date: str,
    status: int,
) -> None:
    # Red when: a subjects route calls datetime.now itself instead of taking get_now.
    set_now(instant)
    _, headers = signed_in(db_session)
    response = client.post(
        "/v1/subjects", json={"name": "Mạng máy tính", "exam_date": exam_date}, headers=headers
    )
    assert response.status_code == status


def test_r23_days_until_exam_follows_the_injected_clock(
    client: TestClient, db_session: Session, set_now: Callable[[datetime], None]
) -> None:
    _, headers = signed_in(db_session)
    set_now(AT_0359)
    created = client.post(
        "/v1/subjects", json={"name": "Mạng", "exam_date": "2026-10-30"}, headers=headers
    ).json()
    assert created["days_until_exam"] == 8
    set_now(AT_0400)
    assert client.get("/v1/subjects", headers=headers).json()[0]["days_until_exam"] == 7
