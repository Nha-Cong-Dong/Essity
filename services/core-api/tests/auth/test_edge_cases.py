"""Edge cases found by the independent tester for T1.8-T1.10 (each names the change it catches).

The constants of rules the spec states in numbers are pinned here with literals: tests that read
`auth.X.limit` or `UNVERIFIED_LIFETIME` pass for any value of it.
"""

import json
import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.api import auth
from core_api.db.models import AuthSession, User
from core_api.domain.auth.passwords import hash_password
from core_api.domain.auth.tokens import TokenPurpose, hash_token
from core_api.repositories.email_token import EmailTokenRepository
from core_api.repositories.user import UserRepository
from core_api.security.audit import IP_HASH_LENGTH, hash_ip

PASSWORD = "ngựa vằn ăn cỏ buổi sáng"
WRONG = "không phải mật khẩu này"


def make_user(session: Session) -> User:
    user = UserRepository(session).create(
        f"edge-{uuid.uuid4().hex[:12]}@example.com", hash_password(PASSWORD)
    )
    user.email_verified_at = user.created_at
    session.flush()
    return user


def login(client: TestClient, email: str, password: str, **kwargs: object) -> int:
    body = {"email": email, "password": password}
    return client.post("/v1/auth/login", json=body, **kwargs).status_code  # pyright: ignore[reportArgumentType]


# --- Pinned numbers (spec / ADR-0020 / A10) ----------------------------------------------------


def test_rule_numbers_are_the_ones_the_spec_states() -> None:
    """Catches: any change of a limit or window constant (tests elsewhere read the constant)."""
    assert (auth.LOGIN_PER_EMAIL_IP.limit, auth.LOGIN_PER_EMAIL_IP.window) == (
        5,
        timedelta(minutes=15),
    )
    assert (auth.LOGIN_PER_EMAIL.limit, auth.LOGIN_PER_EMAIL.window) == (
        20,
        timedelta(minutes=15),
    )
    assert (auth.RESET_PER_IP.limit, auth.RESET_PER_IP.window) == (10, timedelta(hours=1))
    assert (auth.CONFIRM_PER_IP.limit, auth.CONFIRM_PER_IP.window) == (30, timedelta(hours=1))
    assert auth.EMAIL_COOLDOWN.period == timedelta(seconds=60)


def test_ip_hash_is_16_hex_characters() -> None:
    """Catches: IP_HASH_LENGTH changed (a longer hash makes the IP easier to confirm)."""
    assert IP_HASH_LENGTH == 16
    assert len(hash_ip("203.0.113.7", b"k" * 32)) == 16


# --- Login ---------------------------------------------------------------------------------


def test_failures_of_one_email_do_not_lock_another_email_from_the_same_ip(
    client: TestClient, db_session: Session
) -> None:
    """Catches: the pair key built from the IP alone (a dormitory NAT locked by one person)."""
    alice, bob = make_user(db_session), make_user(db_session)
    for _ in range(6):
        login(client, alice.email, WRONG)
    assert login(client, alice.email, PASSWORD) == 429
    assert login(client, bob.email, PASSWORD) == 200


def test_login_with_a_very_long_user_agent_still_works_and_is_truncated(
    client: TestClient, db_session: Session
) -> None:
    """Catches: `user_agent[:USER_AGENT_MAX]` removed (the 256-char column would overflow: 500)."""
    user = make_user(db_session)
    status = login(client, user.email, PASSWORD, headers={"User-Agent": "x" * 5000})
    assert status == 200
    stored = db_session.scalars(
        select(AuthSession.user_agent).where(AuthSession.user_id == user.id)
    )
    assert [len(value or "") for value in stored] == [256]


def test_login_success_event_names_the_user(
    client: TestClient, db_session: Session, log_output: Callable[[], str]
) -> None:
    """Catches: `set_user_id` dropped from login (the login dependency never runs, so the
    security line `login_success` would have no user_id)."""
    user = make_user(db_session)
    assert login(client, user.email, PASSWORD) == 200
    [line] = [
        line
        for line in (json.loads(raw) for raw in log_output().splitlines() if raw.startswith("{"))
        if line.get("event") == "login_success"
    ]
    assert line["user_id"] == str(user.id)


def test_login_rejects_missing_fields_and_over_long_password_without_counting_hashing(
    client: TestClient,
) -> None:
    """Catches: the body limits removed (a 1 MB password would be hashed by argon2)."""
    assert client.post("/v1/auth/login", json={"email": "a@example.com"}).status_code == 422
    assert login(client, "a@example.com", "x" * 1025) == 422


# --- Reset confirm -------------------------------------------------------------------------


def test_confirm_with_a_verify_token_and_a_weak_password_answers_400_not_422(
    client: TestClient, db_session: Session
) -> None:
    """Catches: `owner_of_live` without the purpose filter (a live verify-email token would get
    a 422 'too_short', telling its holder apart from an unknown token)."""
    user = make_user(db_session)
    raw = EmailTokenRepository(db_session).issue(user.id, TokenPurpose.VERIFY_EMAIL)
    db_session.flush()
    response = client.post("/v1/auth/password-reset/confirm", json={"token": raw, "password": "x"})
    assert (response.status_code, response.json()) == (400, {"detail": "invalid_or_expired_token"})
    assert hash_token(raw)  # the token itself is untouched by the refusal
    still_live = EmailTokenRepository(db_session).owner_of_live(
        raw, TokenPurpose.VERIFY_EMAIL, user.created_at
    )
    assert still_live == user.id


@pytest.mark.parametrize("password", ["", "a" * 7])
def test_confirm_refuses_empty_or_7_character_passwords_and_keeps_the_token(
    client: TestClient, db_session: Session, password: str
) -> None:
    """Catches: the password rules skipped on confirm (empty password accepted)."""
    user = make_user(db_session)
    raw = EmailTokenRepository(db_session).issue(user.id, TokenPurpose.RESET_PASSWORD)
    db_session.flush()
    first = client.post(
        "/v1/auth/password-reset/confirm", json={"token": raw, "password": password}
    )
    assert first.status_code == 422
    ok = client.post(
        "/v1/auth/password-reset/confirm", json={"token": raw, "password": PASSWORD + "!"}
    )
    assert ok.status_code == 200
