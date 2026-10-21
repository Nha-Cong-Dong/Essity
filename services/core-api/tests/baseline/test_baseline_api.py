"""T1.17: `/v1/baseline` and the `/v1/me` flags (US-11 AC1–AC3, AC5; ADR-0001, ADR-0013,
ADR-0014; plan B1–B9, B14, B16).

Time is moved by back-dating the stored columns (`email_verified_at`, `entered_at`); the exact
seven-day boundaries are in test_baseline_domain.py.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.repositories.subject import SubjectRepository

VALID: dict[str, Any] = {"gpa_before": "2.85", "prior_ready_days": 3}


def me(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get("/v1/me", headers=headers)
    assert response.status_code == 200
    return response.json()


def post(client: TestClient, headers: dict[str, str], body: dict[str, Any] = VALID) -> Any:
    return client.post("/v1/baseline", json=body, headers=headers)


# --- /v1/me (AC1, AC2, B1, B14) ---------------------------------------------------------------


def test_ac1_verified_account_without_baseline_needs_one(
    client: TestClient, db_session: Session
) -> None:
    _, headers = signed_in(db_session)
    body = me(client, headers)
    assert (body["needs_baseline"], body["has_subjects"]) == (True, False)


def test_ac1_unverified_account_is_not_asked_yet(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session, verified=False)
    assert me(client, headers)["needs_baseline"] is False


def test_b14_has_subjects_once_a_subject_exists(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    SubjectRepository(db_session, user.id).create("Mạng máy tính")
    db_session.flush()
    assert me(client, headers)["has_subjects"] is True


def test_b14_a_deleted_subject_does_not_count(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    subjects = SubjectRepository(db_session, user.id)
    subject = subjects.create("Mạng máy tính")
    db_session.flush()
    subjects.soft_delete(subject.id)
    db_session.flush()
    assert me(client, headers)["has_subjects"] is False


def test_ac1_after_entering_the_baseline_it_is_no_longer_needed(
    client: TestClient, db_session: Session
) -> None:
    _, headers = signed_in(db_session)
    assert post(client, headers).status_code == 201
    assert me(client, headers)["needs_baseline"] is False


# --- POST (AC1, AC2, AC3, PLAN T1.17) ---------------------------------------------------------


def test_ac1_post_returns_the_baseline(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    response = post(client, headers)
    assert response.status_code == 201
    body = response.json()
    assert body["gpa_before"] == "2.85"  # a string: no float rounding on the way (B7)
    assert (body["prior_ready_days"], body["prior_days_unknown"]) == (3, False)
    assert (body["is_late"], body["locked"]) == (False, False)
    entered = datetime.fromisoformat(body["entered_at"])
    assert datetime.fromisoformat(body["editable_until"]) == entered + timedelta(days=7)
    assert abs(entered - datetime.now(UTC)) < timedelta(minutes=1)
    assert "gpa_after" not in body


def test_ac1_dont_remember_stores_zero_days_and_the_flag(
    client: TestClient, db_session: Session
) -> None:
    _, headers = signed_in(db_session)
    response = post(client, headers, {"gpa_before": "3.00", "prior_days_unknown": True})
    assert response.status_code == 201
    assert (response.json()["prior_ready_days"], response.json()["prior_days_unknown"]) == (0, True)


def test_b8_dont_remember_with_a_count_is_refused(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    body = {"gpa_before": "3.00", "prior_ready_days": 4, "prior_days_unknown": True}
    assert post(client, headers, body).status_code == 422


def test_plan_t1_17_baseline_cannot_be_entered_twice(
    client: TestClient, db_session: Session
) -> None:
    _, headers = signed_in(db_session)
    assert post(client, headers).status_code == 201
    second = post(client, headers, {"gpa_before": "4.00", "prior_ready_days": 9})
    assert (second.status_code, second.json()) == (409, {"detail": "baseline_already_exists"})
    assert client.get("/v1/baseline", headers=headers).json()["gpa_before"] == "2.85"


def test_ac2_entered_more_than_seven_days_after_verifying_is_late(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    user.email_verified_at = datetime.now(UTC) - timedelta(days=7, minutes=1)
    db_session.flush()
    assert post(client, headers).json()["is_late"] is True


def test_ac2_entered_within_seven_days_of_verifying_is_on_time(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    user.email_verified_at = datetime.now(UTC) - timedelta(days=6, hours=23)
    db_session.flush()
    assert post(client, headers).json()["is_late"] is False


@pytest.mark.parametrize("field", ["entered_at", "is_late", "user_id", "gpa_after", "locked"])
def test_ac2_b16_server_fields_cannot_be_sent(
    client: TestClient, db_session: Session, field: str
) -> None:
    _, headers = signed_in(db_session)
    body = {**VALID, field: "2026-01-01T00:00:00Z" if field == "entered_at" else False}
    assert post(client, headers, body).status_code == 422


@pytest.mark.parametrize("gpa", [0, 4, "0.00", "4.00", 2.85, "2.85", "3"])
def test_ac3_gpa_in_range_is_accepted(client: TestClient, db_session: Session, gpa: object) -> None:
    _, headers = signed_in(db_session)
    assert post(client, headers, {"gpa_before": gpa, "prior_ready_days": 0}).status_code == 201


@pytest.mark.parametrize(
    "gpa",
    [-0.01, 4.01, "4.001", 2.857, "abc", "NaN", "Infinity", "-Infinity", "2,85", None, True, ""],
)
def test_ac3_gpa_out_of_range_or_malformed_is_422(
    client: TestClient, db_session: Session, gpa: object
) -> None:
    _, headers = signed_in(db_session)
    response = post(client, headers, {"gpa_before": gpa, "prior_ready_days": 0})
    assert response.status_code == 422


@pytest.mark.parametrize("days", [-1, 1.5, 366, 10**12, "many", None])
def test_ac3_days_out_of_range_or_malformed_is_422(
    client: TestClient, db_session: Session, days: object
) -> None:
    _, headers = signed_in(db_session)
    response = post(client, headers, {"gpa_before": "2.00", "prior_ready_days": days})
    assert response.status_code == 422


@pytest.mark.parametrize("days", [0, 365])
def test_b9_days_bounds_are_accepted(client: TestClient, db_session: Session, days: int) -> None:
    _, headers = signed_in(db_session)
    assert (
        post(client, headers, {"gpa_before": "2.00", "prior_ready_days": days}).status_code == 201
    )


def test_gpa_is_required(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    assert post(client, headers, {"prior_ready_days": 2}).status_code == 422


def test_ac3_error_does_not_echo_the_gpa(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    response = post(client, headers, {"gpa_before": "4.37", "prior_ready_days": 0})
    assert response.status_code == 422
    assert "4.37" not in response.text


# --- GET --------------------------------------------------------------------------------------


def test_get_without_a_baseline_is_404(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    response = client.get("/v1/baseline", headers=headers)
    assert (response.status_code, response.json()) == (404, {"detail": "baseline_not_found"})


def test_get_returns_the_baseline_and_is_not_cached(
    client: TestClient, db_session: Session
) -> None:
    _, headers = signed_in(db_session)
    posted = post(client, headers).json()
    response = client.get("/v1/baseline", headers=headers)
    assert response.status_code == 200
    assert response.json() == posted
    assert response.headers["cache-control"] == "no-store"


# --- PUT (AC5, B5) ----------------------------------------------------------------------------


def test_ac5_put_within_seven_days_replaces_and_keeps_entered_at_and_is_late(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    user.email_verified_at = datetime.now(UTC) - timedelta(days=8)
    db_session.flush()
    posted = post(client, headers).json()
    response = client.put(
        "/v1/baseline", json={"gpa_before": "3.10", "prior_days_unknown": True}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["gpa_before"], body["prior_ready_days"], body["prior_days_unknown"]) == (
        "3.10",
        0,
        True,
    )
    assert (body["entered_at"], body["is_late"]) == (posted["entered_at"], True)


def test_ac5_put_after_seven_days_is_locked(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    assert post(client, headers).status_code == 201
    db_session.execute(
        text("UPDATE baseline SET entered_at = :at WHERE user_id = :user_id"),
        {"at": datetime.now(UTC) - timedelta(days=7, seconds=1), "user_id": user.id},
    )
    db_session.expire_all()
    response = client.put("/v1/baseline", json={"gpa_before": "4.00"}, headers=headers)
    assert (response.status_code, response.json()) == (409, {"detail": "baseline_locked"})
    body = client.get("/v1/baseline", headers=headers).json()
    assert (body["gpa_before"], body["locked"]) == ("2.85", True)


def test_ac5_put_without_a_baseline_is_404(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    response = client.put("/v1/baseline", json=VALID, headers=headers)
    assert (response.status_code, response.json()) == (404, {"detail": "baseline_not_found"})


def test_ac3_put_validates_like_post(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    post(client, headers)
    response = client.put("/v1/baseline", json={"gpa_before": "4.01"}, headers=headers)
    assert response.status_code == 422


# --- Skip (AC2, B1–B3) ------------------------------------------------------------------------


def test_ac2_asked_again_after_one_skip_then_never(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    answers = [client.post("/v1/baseline/skip", headers=headers).json() for _ in range(3)]
    assert answers == [
        {"needs_baseline": True},
        {"needs_baseline": False},
        {"needs_baseline": False},
    ]
    assert me(client, headers)["needs_baseline"] is False


def test_ac2_after_skipping_twice_the_baseline_can_still_be_entered(
    client: TestClient, db_session: Session
) -> None:
    _, headers = signed_in(db_session)
    for _ in range(2):
        client.post("/v1/baseline/skip", headers=headers)
    assert post(client, headers).status_code == 201


def test_b3_skip_with_a_baseline_changes_nothing(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    post(client, headers)
    response = client.post("/v1/baseline/skip", headers=headers)
    assert (response.status_code, response.json()) == (200, {"needs_baseline": False})
    db_session.refresh(user)
    assert user.baseline_skips == 0


# --- Isolation (ADR-0001) and unverified accounts (T1.9) ---------------------------------------


def test_adr_0001_bob_cannot_read_or_change_alices_baseline(
    client: TestClient, db_session: Session
) -> None:
    _, alice = signed_in(db_session)
    _, bob = signed_in(db_session)
    post(client, alice)

    assert client.get("/v1/baseline", headers=bob).status_code == 404
    assert client.put("/v1/baseline", json={"gpa_before": "0.10"}, headers=bob).status_code == 404
    assert post(client, bob, {"gpa_before": "1.00"}).status_code == 201
    assert client.post("/v1/baseline/skip", headers=bob).status_code == 200

    assert client.get("/v1/baseline", headers=alice).json()["gpa_before"] == "2.85"
    assert client.get("/v1/baseline", headers=bob).json()["gpa_before"] == "1.00"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/baseline"),
        ("POST", "/v1/baseline"),
        ("PUT", "/v1/baseline"),
        ("POST", "/v1/baseline/skip"),
    ],
)
def test_t1_9_unverified_account_is_refused(
    client: TestClient, db_session: Session, method: str, path: str
) -> None:
    _, headers = signed_in(db_session, verified=False)
    response = client.request(method, path, json=VALID, headers=headers)
    assert (response.status_code, response.json()) == (403, {"detail": "email_not_verified"})


def test_not_signed_in_is_401(client: TestClient) -> None:
    assert client.get("/v1/baseline").status_code == 401


# --- Logs (ADR-0013) --------------------------------------------------------------------------


def test_adr_0013_gpa_never_reaches_the_logs(
    client: TestClient, db_session: Session, log_output: Any
) -> None:
    _, headers = signed_in(db_session)
    post(client, headers, {"gpa_before": "3.27", "prior_ready_days": 41})
    client.put("/v1/baseline", json={"gpa_before": "3.28"}, headers=headers)
    client.put("/v1/baseline", json={"gpa_before": "4.37"}, headers=headers)
    logs = log_output()
    assert logs  # the requests did log something
    for value in ("3.27", "3.28", "4.37"):
        assert value not in logs
