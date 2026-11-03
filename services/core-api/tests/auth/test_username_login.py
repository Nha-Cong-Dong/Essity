"""T1.23 (part 3): `POST /v1/auth/login` by username or email (D3).

Rules under test: D3 (identifier with `@` is an email, otherwise a username; a phone number is
not accepted; the old `email` field still works), AC5 (one 401, the same work for every kind of
failure), AC6 + ADR-0020 (limits by identifier+IP and by identifier), ADR-0013 (no identifier in
the logs, only a keyed hash).
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import fresh_username
from core_api.api import auth
from core_api.db.models import User
from core_api.domain.auth.passwords import hash_password
from core_api.repositories.user import UserRepository
from core_api.security.audit import hash_ip
from core_api.security.client_ip import CLIENT_IP_HEADER
from ips import fresh_ip

LOGIN = "/v1/auth/login"
PASSWORD = "ngựa vằn ăn cỏ buổi sáng"
WRONG = "không phải mật khẩu này"
BAD = (401, {"detail": "invalid_credentials"})


def make_user(session: Session, *, username: str | None = None, phone: str | None = None) -> User:
    user = UserRepository(session).create(
        f"lg-{uuid.uuid4().hex[:12]}@example.com",
        hash_password(PASSWORD),
        username=username or fresh_username(),
        phone=phone,
    )
    user.email_verified_at = user.created_at
    session.flush()
    return user


def sign_in(
    client: TestClient, field: str, value: str, password: str = PASSWORD
) -> tuple[int, dict[str, object]]:
    response = client.post(LOGIN, json={field: value, "password": password})
    return response.status_code, response.json()


def test_d3_login_by_username(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    status, body = sign_in(client, "identifier", user.username)
    assert status == 200 and set(body) == {"token", "expires_at", "email_verified"}


def test_d3_login_by_email_through_identifier(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    assert sign_in(client, "identifier", user.email)[0] == 200


def test_d3_the_old_email_field_is_still_accepted_for_one_round(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    assert sign_in(client, "email", user.email)[0] == 200


def test_d3_neither_field_is_422(client: TestClient) -> None:
    assert client.post(LOGIN, json={"password": PASSWORD}).status_code == 422


def test_d3_the_identifier_is_trimmed_and_lowercased(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session, username="bob.smith" + uuid.uuid4().hex[:4])
    assert sign_in(client, "identifier", f"  {user.username.upper()} ")[0] == 200
    assert sign_in(client, "identifier", f" {user.email.upper()} ")[0] == 200


def test_d3_a_phone_number_is_not_a_login_key(client: TestClient, db_session: Session) -> None:
    # Red when: the phone is looked up as an identifier.
    make_user(db_session, phone="+84912345678")
    for typed in ("+84912345678", "0912345678", "84912345678"):
        assert sign_in(client, "identifier", typed) == BAD


def test_ac5_every_kind_of_failure_is_the_same_401(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    answers = [
        sign_in(client, "identifier", user.username, WRONG),
        sign_in(client, "identifier", user.email, WRONG),
        sign_in(client, "identifier", fresh_username()),
        sign_in(client, "identifier", f"nobody-{uuid.uuid4().hex[:8]}@example.com"),
    ]
    assert answers == [BAD] * 4


@pytest.mark.parametrize("kind", ["username", "email"])
def test_ac5_an_unknown_name_still_runs_the_dummy_hash(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    calls: list[str] = []

    def counting(password: str) -> None:
        calls.append(password)

    monkeypatch.setattr(auth, "dummy_verify", counting)
    unknown = fresh_username() if kind == "username" else f"x-{uuid.uuid4().hex[:8]}@example.com"
    assert sign_in(client, "identifier", unknown, WRONG)[0] == 401
    assert calls == [WRONG]


def test_ac6_five_failures_per_username_and_ip_then_429(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    statuses = [sign_in(client, "identifier", user.username, WRONG)[0] for _ in range(5)]
    assert statuses == [401] * 5
    assert sign_in(client, "identifier", user.username)[0] == 429


def test_ac6_spelling_variants_of_one_username_share_one_counter(
    client: TestClient, db_session: Session
) -> None:
    # Red when: the raw text, not the normalized name, is the rate-limit key.
    user = make_user(db_session)
    variants = [user.username, user.username.upper(), f" {user.username} ", user.username.title()]
    for typed in variants + [user.username]:
        assert sign_in(client, "identifier", typed, WRONG)[0] == 401
    assert sign_in(client, "identifier", f"  {user.username.upper()}")[0] == 429


def test_ac6_twenty_failures_per_username_across_ips_block_any_ip(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    for _ in range(auth.LOGIN_PER_IDENTIFIER.limit):
        response = client.post(
            LOGIN,
            json={"identifier": user.username, "password": WRONG},
            headers={CLIENT_IP_HEADER: fresh_ip("172.17")},
        )
        assert response.status_code == 401
    response = client.post(
        LOGIN,
        json={"identifier": user.username, "password": PASSWORD},
        headers={CLIENT_IP_HEADER: fresh_ip("172.17")},
    )
    assert response.status_code == 429


def test_ac6_a_correct_username_login_gives_its_attempt_back(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    statuses = [sign_in(client, "identifier", user.username)[0] for _ in range(8)]
    assert statuses == [200] * 8


def test_adr0013_what_was_typed_is_logged_only_as_a_keyed_hash(
    client: TestClient, db_session: Session, log_output: Callable[[], str]
) -> None:
    # The login box may hold a username or a password typed in the wrong place.
    typed = "hunter" + uuid.uuid4().hex[:8]
    assert sign_in(client, "identifier", typed, WRONG)[0] == 401
    user = make_user(db_session, phone="+84912345678")
    assert sign_in(client, "identifier", user.username, WRONG)[0] == 401
    output = log_output()
    assert typed not in output and user.username not in output
    assert "912345678" not in output
    assert hash_ip(typed) in output
