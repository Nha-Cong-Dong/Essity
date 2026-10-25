"""T1.7 (part 3): `POST /v1/auth/register` and `POST /v1/auth/verify-email/resend`.

Rules under test, each named in its test: US-12 AC1 (password rules, with the reason), AC2
(verification email through the job), AC5 (one answer whether the email exists or not, same
work done), AC6 (sign-ups limited per IP), AC8 (no password or address in the logs), ADR-0014
(≥ 60 s between emails to one address), ADR-0019 §2 (an existing account, verified or not, gets
"account exists" and keeps its password).
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from core_api.api import auth
from core_api.db.models import User
from core_api.domain.auth.passwords import hash_password, verify_password
from core_api.repositories.user import UserRepository
from ips import fresh_ip

REGISTER = "/v1/auth/register"
RESEND = "/v1/auth/verify-email/resend"
PASSWORD = "ngựa vằn ăn cỏ buổi sáng"  # long, no digits or capitals: allowed (AC1)


def new_email() -> str:
    return f"new-{uuid.uuid4().hex[:12]}@example.com"


def register(client: TestClient, email: str, password: str = PASSWORD) -> tuple[int, object]:
    response = client.post(REGISTER, json={"email": email, "password": password})
    return response.status_code, response.json()


def queued_emails(session: Session) -> list[dict[str, str]]:
    """Payloads of `send_email` jobs queued in the test's transaction (rolled back after)."""
    rows = session.execute(
        text("SELECT args FROM procrastinate_jobs WHERE task_name = 'send_email' ORDER BY id")
    ).scalars()
    return [row["payload"] for row in rows]


def existing_user(session: Session, *, verified: bool) -> User:
    user = UserRepository(session).create(new_email(), hash_password("mật khẩu cũ của chủ thật"))
    if verified:
        user.email_verified_at = user.created_at
    session.flush()
    return user


# --- Register ---------------------------------------------------------------------------------


def test_ac2_register_creates_an_unverified_account_and_queues_its_verification_email(
    client: TestClient, db_session: Session
) -> None:
    email = new_email()
    assert register(client, email) == (202, {"status": "check_email"})

    user = UserRepository(db_session).get_by_email(email)
    assert user is not None
    assert user.email_verified_at is None
    assert user.password_hash is not None and verify_password(user.password_hash, PASSWORD)
    assert queued_emails(db_session) == [{"user_id": str(user.id), "email": "verify_email"}]


@pytest.mark.parametrize("verified", [True, False])
def test_ac5_adr0019_an_existing_account_gets_the_same_answer_and_keeps_its_password(
    client: TestClient, db_session: Session, verified: bool
) -> None:
    owner = existing_user(db_session, verified=verified)
    old_hash = owner.password_hash

    assert register(client, owner.email) == register(client, new_email())

    db_session.refresh(owner)
    assert owner.password_hash == old_hash
    assert {"user_id": str(owner.id), "email": "account_exists"} in queued_emails(db_session)


def test_ac5_an_existing_email_costs_the_same_password_hash(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The new-account path hashes the password (argon2, ~tens of ms); skipping it for an
    # existing email would let response time tell the two apart.
    hashed: list[str] = []

    def counting_hash(password: str) -> str:
        hashed.append(password)
        return "not-a-real-hash"

    monkeypatch.setattr(auth, "hash_password", counting_hash)
    owner = existing_user(db_session, verified=True)
    register(client, owner.email)
    assert hashed == [PASSWORD]


def test_the_address_is_normalized_so_case_cannot_create_a_second_account(
    client: TestClient, db_session: Session
) -> None:
    email = new_email()
    assert register(client, f"  {email.upper()} ")[0] == 202
    owner = UserRepository(db_session).get_by_email(email)
    assert owner is not None and owner.email == email  # stored lowercase, trimmed
    # The same address in another case is the same address: its 60 s cooldown applies.
    assert register(client, email)[0] == 429
    assert len(queued_emails(db_session)) == 1


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("ngắn", "too_short"),
        ("x" * 129, "too_long"),
        ("password123", "common"),
    ],
)
def test_ac1_a_weak_password_is_refused_with_its_reason_and_creates_nothing(
    client: TestClient, db_session: Session, password: str, reason: str
) -> None:
    email = new_email()
    assert register(client, email, password) == (422, {"detail": reason})
    assert UserRepository(db_session).get_by_email(email) is None
    assert queued_emails(db_session) == []


def test_adr0019_a_password_equal_to_the_address_is_refused(client: TestClient) -> None:
    email = new_email()
    assert register(client, email, email.split("@")[0]) == (422, {"detail": "same_as_email"})


def test_ac5_a_weak_password_is_refused_the_same_for_an_existing_email(
    client: TestClient, db_session: Session
) -> None:
    # Password rules come first: otherwise "422" vs "202" would tell which emails exist.
    owner = existing_user(db_session, verified=True)
    assert register(client, owner.email, "ngắn") == register(client, new_email(), "ngắn")


@pytest.mark.parametrize(
    "email", ["", "no-at-sign", "a@b", "two@@example.com", "x" * 320 + "@a.vn"]
)
def test_a_malformed_address_is_refused(client: TestClient, email: str) -> None:
    assert register(client, email)[0] == 422


def test_ac6_sign_ups_are_limited_per_ip(client: TestClient, client_ip: str) -> None:
    for _ in range(auth.REGISTER_PER_IP.limit):
        assert register(client, new_email())[0] == 202
    status = client.post(REGISTER, json={"email": new_email(), "password": PASSWORD})
    assert status.status_code == 429
    assert int(status.headers["Retry-After"]) > 0
    # Another fresh address: Redis is shared across runs, a fixed one would fill up.
    other_ip = {"X-Client-IP": fresh_ip("172.16")}
    response = client.post(
        REGISTER, json={"email": new_email(), "password": PASSWORD}, headers=other_ip
    )
    assert response.status_code == 202


# --- Resend -----------------------------------------------------------------------------------


def resend(client: TestClient, email: str) -> tuple[int, object]:
    response = client.post(RESEND, json={"email": email})
    return response.status_code, response.json()


def test_ac2_resend_queues_a_new_verification_email_for_an_unverified_account(
    client: TestClient, db_session: Session
) -> None:
    owner = existing_user(db_session, verified=False)
    assert resend(client, owner.email) == (202, {"status": "check_email"})
    assert queued_emails(db_session) == [{"user_id": str(owner.id), "email": "verify_email"}]


def test_ac5_resend_answers_the_same_and_sends_nothing_for_unknown_or_verified(
    client: TestClient, db_session: Session
) -> None:
    verified = existing_user(db_session, verified=True)
    unverified = existing_user(db_session, verified=False)
    answers = [resend(client, email) for email in (new_email(), verified.email, unverified.email)]
    assert answers == [(202, {"status": "check_email"})] * 3
    assert [job["user_id"] for job in queued_emails(db_session)] == [str(unverified.id)]


def test_adr0014_emails_to_one_address_are_at_least_60_seconds_apart(
    client: TestClient, db_session: Session
) -> None:
    email = new_email()
    assert register(client, email)[0] == 202
    response = client.post(RESEND, json={"email": email})
    assert response.status_code == 429
    assert 0 < int(response.headers["Retry-After"]) <= 60
    assert len(queued_emails(db_session)) == 1


# --- Logs -------------------------------------------------------------------------------------


def test_ac8_neither_the_password_nor_the_address_reaches_the_logs(
    client: TestClient, log_output: Callable[[], str]
) -> None:
    email = new_email()
    register(client, email)
    register(client, email, "ngắn")
    output = log_output()
    assert PASSWORD not in output
    assert email.split("@")[0] not in output


# --- Review of PR #7 --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"password": "SECRET-PASSWORD-xyz"},  # no email
        {"email": "not-an-address", "password": "SECRET-PASSWORD-xyz"},
        {"email": "a@example.com", "password": "SECRET-PASSWORD-xyz" * 60},  # over 1024
    ],
)
def test_a_malformed_request_never_echoes_the_password(
    client: TestClient, body: dict[str, str]
) -> None:
    # FastAPI's default 422 sends the caller's input back; web or a proxy may log it.
    response = client.post(REGISTER, json=body)
    assert response.status_code == 422
    assert "SECRET-PASSWORD" not in response.text


def test_ac6_resend_is_limited_per_ip(client: TestClient) -> None:
    for _ in range(auth.RESEND_PER_IP.limit):
        assert resend(client, new_email())[0] == 202
    assert resend(client, new_email())[0] == 429


def test_ac6_weak_passwords_do_not_use_up_the_sign_up_quota(client: TestClient) -> None:
    # Only sign-ups that pass the password rules count: a typo should not lock a dormitory out.
    for _ in range(auth.REGISTER_PER_IP.limit + 2):
        assert register(client, new_email(), "ngắn")[0] == 422
    assert register(client, new_email())[0] == 202
