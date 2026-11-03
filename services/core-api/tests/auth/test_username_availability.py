"""T1.23: `GET /v1/auth/username-availability` (D8): the sign-up form asks when the field is left.

Rules under test: D2 (same shape and reserved rules as sign-up, case-insensitive), AC5 (a name held
by a sign-up with an existing email reads "taken" like a real one: review P1), AC6 (limited per
IP, no session needed).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import fresh_username
from core_api.api import auth
from core_api.domain.auth.passwords import hash_password
from core_api.repositories.user import UserRepository
from core_api.security.client_ip import CLIENT_IP_HEADER
from core_api.security.rate_limit import RateLimiter, RateLimiterUnavailableError
from ips import fresh_ip

CHECK = "/v1/auth/username-availability"


def check(client: TestClient, name: str, ip: str | None = None) -> tuple[int, dict[str, object]]:
    headers = {CLIENT_IP_HEADER: ip} if ip else {}
    response = client.get(CHECK, params={"u": name}, headers=headers)
    return response.status_code, response.json()


def test_d8_a_free_name_is_available(client: TestClient) -> None:
    assert check(client, fresh_username()) == (200, {"available": True, "reason": None})


def test_d8_a_taken_name_is_taken_whatever_the_case(
    client: TestClient, db_session: Session
) -> None:
    name = fresh_username()
    UserRepository(db_session).create("avail1@example.com", username=name)
    db_session.flush()
    expected = (200, {"available": False, "reason": "taken"})
    assert check(client, name) == expected
    assert check(client, f" {name.upper()} ") == expected


@pytest.mark.parametrize(
    ("name", "reason"),
    [("ab", "invalid"), ("1abc", "invalid"), ("a..b", "invalid"), ("", "invalid"),
     ("admin", "reserved"), ("Support", "reserved")],
)  # fmt: skip
def test_d2_a_name_the_rules_refuse_says_why(client: TestClient, name: str, reason: str) -> None:
    assert check(client, name) == (200, {"available": False, "reason": reason})


def test_ac5_a_name_held_by_a_taken_email_reads_taken(
    client: TestClient, db_session: Session
) -> None:
    owner = UserRepository(db_session).create("avail2@example.com", hash_password("mật khẩu chủ"))
    db_session.flush()
    probe = fresh_username()
    body = {"email": owner.email, "password": "ngựa vằn ăn cỏ buổi sáng", "username": probe}
    assert client.post("/v1/auth/register", json=body).status_code == 202
    assert check(client, probe) == (200, {"available": False, "reason": "taken"})


def test_ac6_it_is_limited_per_ip_and_needs_no_session(client: TestClient) -> None:
    ip = fresh_ip("172.18")
    statuses = [
        check(client, fresh_username(), ip)[0] for _ in range(auth.USERNAME_CHECK_PER_IP.limit)
    ]
    assert statuses == [200] * auth.USERNAME_CHECK_PER_IP.limit
    assert check(client, fresh_username(), ip)[0] == 429
    assert check(client, fresh_username(), fresh_ip("172.18"))[0] == 200  # another IP is not


def test_a_control_character_in_the_name_is_422(client: TestClient) -> None:
    assert client.get(CHECK, params={"u": "ab\x00c"}).status_code == 422


def test_ac5_a_failing_hold_lookup_is_503_not_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: the endpoint swallows a Redis error and answers "available".
    def broken(self: RateLimiter, *args: object) -> bool:
        raise RateLimiterUnavailableError

    monkeypatch.setattr(RateLimiter, "is_reserved", broken)
    assert client.get(CHECK, params={"u": fresh_username()}).status_code == 503
