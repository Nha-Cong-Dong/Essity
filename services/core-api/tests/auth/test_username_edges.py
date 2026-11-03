# redis-py's ttl/scan_iter are loosely typed; only the hold tests inspect Redis.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""T1.23 tester: edge cases the coder's tests left open.

The username hold (review P1) failing closed inside the limiter itself, its length and its end;
`identifier` winning over the old `email` field; the per-name counter on the normalized name
across IPs; two accounts; a soft-deleted account's name; two sign-ups racing for one name in
real, separate transactions.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from accounts import fresh_username
from core_api.api import auth
from core_api.clients.redis import redis_from_url
from core_api.db.models import User
from core_api.domain.auth.passwords import hash_password
from core_api.jobs.purge_unverified import UNVERIFIED_LIFETIME
from core_api.repositories.user import UsernameTakenError, UserRepository
from core_api.security.client_ip import CLIENT_IP_HEADER
from core_api.security.rate_limit import (
    KEY_PREFIX,
    Hold,
    RateLimiter,
    RateLimiterUnavailableError,
)
from ips import fresh_ip

LOGIN = "/v1/auth/login"
REGISTER = "/v1/auth/register"
PASSWORD = "ngựa vằn ăn cỏ buổi sáng"
OTHER_PASSWORD = "một mật khẩu khác hẳn"
WRONG = "không phải mật khẩu này"


def new_email() -> str:
    return f"edge-{uuid.uuid4().hex[:12]}@example.com"


def hold(seconds: int = 3600) -> Hold:
    return Hold(f"test-{uuid.uuid4().hex}", timedelta(seconds=seconds))


def dead_limiter() -> RateLimiter:
    return RateLimiter(redis_from_url("redis://127.0.0.1:1/0", timeout=0.2))


# --- The hold itself (security/rate_limit.py) --------------------------------------------------


def test_p1_reserve_with_unreachable_redis_raises() -> None:
    # Red when: `reserve` swallows a Redis error, so a taken email's name is never held and the
    # 202/409 probe of AC5 works again while Redis is down. The API test replaces the method, so
    # it cannot see this.
    with pytest.raises(RateLimiterUnavailableError):
        dead_limiter().reserve(hold(), "bob")


def test_p1_is_reserved_with_unreachable_redis_raises() -> None:
    # Red when: `is_reserved` answers "free" when Redis is down (fail open).
    with pytest.raises(RateLimiterUnavailableError):
        dead_limiter().is_reserved(hold(), "bob")


def test_p1_reserving_again_keeps_the_first_end(redis_client: Redis) -> None:
    # Red when: a second reserve restarts the hold (`nx` dropped), so asking again and again with
    # a taken email keeps a name locked forever.
    limiter, rule = RateLimiter(redis_client), hold(3600)
    limiter.reserve(rule, "bob")
    [key] = list(redis_client.scan_iter(f"{KEY_PREFIX}:{rule.name}:*"))
    redis_client.expire(key, 100)
    limiter.reserve(rule, "bob")
    assert 0 < redis_client.ttl(key) <= 100
    assert limiter.is_reserved(rule, "bob") and not limiter.is_reserved(rule, "alice")


def test_p1_the_hold_lasts_as_long_as_an_unverified_account(
    client: TestClient, db_session: Session, redis_client: Redis
) -> None:
    # Red when: the hold ends before a real unverified sign-up would be purged, so "free again
    # after N minutes" tells a held name from a real account (AC5).
    assert auth.USERNAME_HOLD.period == UNVERIFIED_LIFETIME
    owner = UserRepository(db_session).create(new_email(), hash_password(OTHER_PASSWORD))
    db_session.flush()
    name = fresh_username()
    body = {"email": owner.email, "password": PASSWORD, "username": name}
    assert client.post(REGISTER, json=body).status_code == 202
    key = RateLimiter(redis_client)._hold_key(auth.USERNAME_HOLD, name)  # pyright: ignore[reportPrivateUsage]
    lifetime = int(UNVERIFIED_LIFETIME.total_seconds())
    assert lifetime - 60 < redis_client.ttl(key) <= lifetime


def test_p1_the_hold_is_on_the_normalized_name(client: TestClient, db_session: Session) -> None:
    # Red when: the hold is keyed on the typed text, so "BOB" walks past a hold on "bob".
    owner = UserRepository(db_session).create(new_email(), hash_password(OTHER_PASSWORD))
    db_session.flush()
    name = fresh_username()
    first = {"email": owner.email, "password": PASSWORD, "username": f"  {name.upper()} "}
    assert client.post(REGISTER, json=first).status_code == 202
    again = {"email": new_email(), "password": PASSWORD, "username": name}
    assert client.post(REGISTER, json=again).json() == {"detail": "username_taken"}


# --- Login ---------------------------------------------------------------------------------------


def make_user(session: Session, password: str = PASSWORD) -> User:
    user = UserRepository(session).create(
        new_email(), hash_password(password), username=fresh_username()
    )
    user.email_verified_at = user.created_at
    session.flush()
    return user


def test_d3_identifier_wins_over_the_old_email_field(
    client: TestClient, db_session: Session
) -> None:
    # Red when: with both fields sent, `email` is used: the documented rule is "identifier".
    alice, bob = make_user(db_session), make_user(db_session, OTHER_PASSWORD)
    both = {"identifier": alice.username, "email": bob.email, "password": PASSWORD}
    assert client.post(LOGIN, json=both).status_code == 200
    swapped = {"identifier": bob.username, "email": alice.email, "password": PASSWORD}
    assert client.post(LOGIN, json=swapped).status_code == 401


def test_d3_one_users_name_with_another_users_password_is_refused(
    client: TestClient, db_session: Session
) -> None:
    # Red when: a password is checked against any account rather than the one named.
    alice, bob = make_user(db_session), make_user(db_session, OTHER_PASSWORD)
    for typed in (alice.username, alice.email):
        response = client.post(LOGIN, json={"identifier": typed, "password": OTHER_PASSWORD})
        assert response.json() == {"detail": "invalid_credentials"}
    assert (
        client.post(
            LOGIN, json={"identifier": bob.username, "password": OTHER_PASSWORD}
        ).status_code
        == 200
    )


def test_d3_a_soft_deleted_accounts_name_neither_signs_in_nor_frees_up(
    client: TestClient, db_session: Session
) -> None:
    # Red when: login by username skips the deleted_at check, or a deleted account's name can be
    # taken by someone else while its row still exists (UNIQUE counts it anyway: 500, not 409).
    user = make_user(db_session)
    user.deleted_at = datetime.now(UTC)
    db_session.flush()
    response = client.post(LOGIN, json={"identifier": user.username, "password": PASSWORD})
    assert response.status_code == 401
    body = {"email": new_email(), "password": PASSWORD, "username": user.username}
    assert client.post(REGISTER, json=body).json() == {"detail": "username_taken"}


def test_ac6_the_per_name_counter_uses_the_normalized_name_across_ips(
    client: TestClient, db_session: Session
) -> None:
    # Red when: the 20-per-name counter is keyed on the raw text, so a botnet that changes the
    # case or adds spaces from IP to IP is never stopped (ADR-0020 §2).
    user = make_user(db_session)
    spellings = [user.username, user.username.upper(), f" {user.username}", user.username.title()]
    for attempt in range(auth.LOGIN_PER_IDENTIFIER.limit):
        response = client.post(
            LOGIN,
            json={"identifier": spellings[attempt % len(spellings)], "password": WRONG},
            headers={CLIENT_IP_HEADER: fresh_ip("172.18")},
        )
        assert response.status_code == 401
    response = client.post(
        LOGIN,
        json={"identifier": user.username, "password": PASSWORD},
        headers={CLIENT_IP_HEADER: fresh_ip("172.18")},
    )
    assert response.status_code == 429


def test_repository_finds_a_username_whatever_the_case_and_spaces(db_session: Session) -> None:
    # Red when: `get_by_username` compares the raw text (callers outside the API would miss).
    user = make_user(db_session)
    found = UserRepository(db_session).get_by_username(f"  {user.username.upper()} ")
    assert found is not None and found.id == user.id


# --- Two sign-ups for one name, in real transactions --------------------------------------------


def test_d2_two_concurrent_sign_ups_for_one_name_one_wins_one_is_taken(
    engine: Engine, eraser_engine: Engine
) -> None:
    # Red when: the second INSERT is not told apart as UsernameTakenError once the first commits
    # (a 500 for the loser), or both rows land. Runs in two connections: the second blocks on the
    # unique index until the first commits.
    name = fresh_username()
    outcome: list[str] = []
    first = Session(bind=engine)
    try:
        UserRepository(first).create(new_email(), username=name)
        first.flush()

        def second_sign_up() -> None:
            with Session(bind=engine) as second:
                try:
                    UserRepository(second).create(new_email(), username=name)
                    second.commit()
                    outcome.append("created")
                except UsernameTakenError:
                    second.rollback()
                    outcome.append("taken")

        thread = threading.Thread(target=second_sign_up)
        thread.start()
        thread.join(timeout=0.5)
        assert thread.is_alive()  # waiting on the first transaction's row
        first.commit()
        thread.join(timeout=10)
        assert not thread.is_alive() and outcome == ["taken"]
    finally:
        first.close()
        with eraser_engine.begin() as connection:
            connection.execute(text('DELETE FROM "user" WHERE username = :n'), {"n": name})
