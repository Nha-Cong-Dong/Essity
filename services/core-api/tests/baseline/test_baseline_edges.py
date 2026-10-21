"""T1.17: edge cases found by breaking the code on purpose (mutation testing by the tester).

Each test names the change in `src/` that turns it red.
"""

import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import User
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.user import UserRepository

VALID: dict[str, Any] = {"gpa_before": "2.85", "prior_ready_days": 3}


def post(client: TestClient, headers: dict[str, str], body: dict[str, Any] = VALID) -> Any:
    return client.post("/v1/baseline", json=body, headers=headers)


def error_field(response: Any) -> str:
    assert response.status_code == 422
    return response.json()["detail"][0]["loc"][-1]


def test_b8_dont_remember_with_an_explicit_zero_is_accepted(
    client: TestClient, db_session: Session
) -> None:
    """Red if the rule becomes "unknown requires prior_ready_days to be absent"
    (`not in (None, 0)` -> `not in (None,)`): web may send 0 together with the flag."""
    _, headers = signed_in(db_session)
    body = {"gpa_before": "3.00", "prior_ready_days": 0, "prior_days_unknown": True}
    response = post(client, headers, body)
    assert response.status_code == 201
    assert (response.json()["prior_ready_days"], response.json()["prior_days_unknown"]) == (0, True)


@pytest.mark.parametrize("flag", ["true", "yes", 1, 0, "", None])
def test_b16_dont_remember_flag_must_be_a_real_boolean(
    client: TestClient, db_session: Session, flag: object
) -> None:
    """Red if `StrictBool` becomes `bool` on `prior_days_unknown`: "yes" or 1 would flip it."""
    _, headers = signed_in(db_session)
    body = {"gpa_before": "3.00", "prior_ready_days": 0, "prior_days_unknown": flag}
    assert error_field(post(client, headers, body)) == "prior_days_unknown"


@pytest.mark.parametrize("days", ["3", 3.0, True, False])
def test_b9_days_must_be_a_real_integer(
    client: TestClient, db_session: Session, days: object
) -> None:
    """Red if `strict=True` is dropped from `PriorReadyDays`: "3", 3.0, true pass as 3, 3, 1."""
    _, headers = signed_in(db_session)
    body = {"gpa_before": "2.00", "prior_ready_days": days}
    assert error_field(post(client, headers, body)) == "prior_ready_days"


def test_b7_a_json_number_gpa_is_stored_exactly(client: TestClient, db_session: Session) -> None:
    """Red if the float 2.85 reaches the database as 2.8500000000000000888 or is rounded."""
    _, headers = signed_in(db_session)
    body = {"gpa_before": 2.85, "prior_ready_days": 1}
    assert post(client, headers, body).json()["gpa_before"] == "2.85"
    assert client.get("/v1/baseline", headers=headers).json()["gpa_before"] == "2.85"


def test_b7_a_float_with_binary_noise_is_refused_not_rounded(
    client: TestClient, db_session: Session
) -> None:
    """Red if the GPA is rounded to two decimals instead of refused (0.1 + 0.2)."""
    _, headers = signed_in(db_session)
    body = {"gpa_before": 0.1 + 0.2, "prior_ready_days": 1}
    assert error_field(post(client, headers, body)) == "gpa_before"
    assert client.get("/v1/baseline", headers=headers).status_code == 404


@pytest.mark.parametrize("field", ["entered_at", "is_late", "user_id", "locked"])
def test_ac5_b16_put_refuses_server_fields_and_changes_nothing(
    client: TestClient, db_session: Session, field: str
) -> None:
    """Red if `extra="forbid"` is lost: a PUT could rewrite `is_late` or `entered_at`."""
    _, headers = signed_in(db_session)
    assert post(client, headers).status_code == 201
    body = {"gpa_before": "3.90", "prior_ready_days": 9, field: "2020-01-01T00:00:00Z"}
    assert error_field(client.put("/v1/baseline", json=body, headers=headers)) == field
    assert client.get("/v1/baseline", headers=headers).json()["gpa_before"] == "2.85"


def test_ac5_put_just_inside_the_window_is_accepted(
    client: TestClient, db_session: Session
) -> None:
    """Red if the window shrinks (EDIT_WINDOW 6 days) or `>` becomes `<` in `replace`."""
    user, headers = signed_in(db_session)
    assert post(client, headers).status_code == 201
    db_session.execute(
        text("UPDATE baseline SET entered_at = :at WHERE user_id = :user_id"),
        {"at": datetime.now(UTC) - timedelta(days=6, hours=23, minutes=59), "user_id": user.id},
    )
    db_session.expire_all()
    response = client.put(
        "/v1/baseline", json={"gpa_before": "3.50", "prior_ready_days": 2}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["locked"] is False


def test_ac5_the_baseline_stays_locked_whatever_the_user_sends(
    client: TestClient, db_session: Session
) -> None:
    """Locked: a repeated PUT, and the 404 of another user, never reopen the window."""
    user, headers = signed_in(db_session)
    assert post(client, headers).status_code == 201
    old = datetime.now(UTC) - timedelta(days=30)
    db_session.execute(
        text("UPDATE baseline SET entered_at = :at WHERE user_id = :user_id"),
        {"at": old, "user_id": user.id},
    )
    db_session.expire_all()
    for _ in range(2):
        response = client.put("/v1/baseline", json=VALID, headers=headers)
        assert (response.status_code, response.json()) == (409, {"detail": "baseline_locked"})
    body = client.get("/v1/baseline", headers=headers).json()
    assert datetime.fromisoformat(body["entered_at"]) == old
    assert body["locked"] is True


def test_b14_has_subjects_ignores_other_users_subjects(
    client: TestClient, db_session: Session
) -> None:
    """Red if `SubjectRepository.has_any` loses its `user_id` filter: Bob's subject would
    make Alice skip the "create a subject" step."""
    alice, alice_headers = signed_in(db_session)
    bob, _ = signed_in(db_session)
    SubjectRepository(db_session, bob.id).create_with_exam("Của Bob", date(2099, 1, 1))
    db_session.flush()
    response = client.get("/v1/me", headers=alice_headers)
    assert response.json()["has_subjects"] is False
    assert alice.id != bob.id


def test_b2_skips_of_one_user_never_reach_another_in_me(
    client: TestClient, db_session: Session
) -> None:
    """Red if `record_baseline_skip` loses `User.id == user_id`: Bob's skips would count for all."""
    _, alice = signed_in(db_session)
    _, bob = signed_in(db_session)
    for _ in range(2):
        assert client.post("/v1/baseline/skip", headers=bob).status_code == 200
    assert client.get("/v1/me", headers=alice).json()["needs_baseline"] is True
    assert client.get("/v1/me", headers=bob).json()["needs_baseline"] is False


# --- Skips at the same time (B2: one atomic UPDATE) ---------------------------------------------


@pytest.fixture
def committed_user(engine: Engine) -> Iterator[uuid.UUID]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"skip-{uuid.uuid4().hex[:12]}@example.com")
        session.commit()
        user_id = user.id
    try:
        yield user_id
    finally:
        with Session(engine) as session:
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


def test_b2_concurrent_skips_count_each_one_up_to_the_cap(
    engine: Engine, committed_user: uuid.UUID
) -> None:
    """Red if `record_baseline_skip` becomes read-then-write (lost update: two skips counted
    as one) or loses the `< MAX_SKIPS` guard (CHECK violation: an error in a thread)."""
    barrier = threading.Barrier(4)
    errors: list[BaseException] = []
    counts: list[int] = []

    def skip() -> None:
        try:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                counts.append(UserRepository(session).record_baseline_skip(committed_user))
                session.commit()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=skip) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert all(count in (1, 2) for count in counts)
    with Session(engine) as session:
        stored = session.scalar(select(User.baseline_skips).where(User.id == committed_user))
    assert stored == 2
