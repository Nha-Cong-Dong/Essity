"""T1.8: `POST /v1/auth/login`, the failed-login lock and the security log.

Rules under test, each named in its test: US-12 AC2 (an unverified account can sign in), AC5
(one answer and the same work whether the email exists or not), AC6 and ADR-0020 §2 (5 failures
per email+IP and 20 per email in 15 minutes → 429, counted before hashing, a correct password
does not reset the count), AC7 (a new token at every login), AC8 (32-byte token, only its hash
stored), ADR-0013 (security events logged, no password or token, masked email, keyed IP hash),
ADR-0014 (rehash on login when the parameters have changed).
"""

import json
import random
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session

from core_api.api import auth
from core_api.clients.redis import get_redis, redis_from_url
from core_api.db.models import AuthSession, User
from core_api.domain.auth.passwords import hash_password, needs_rehash, verify_password
from core_api.domain.auth.sessions import SESSION_MAX
from core_api.domain.auth.tokens import TOKEN_BYTES, hash_token
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.user import UserRepository
from core_api.security import rate_limit
from core_api.security.audit import hash_ip
from core_api.security.client_ip import CLIENT_IP_HEADER
from core_api.security.rate_limit import RateLimit, RateLimiter

LOGIN = "/v1/auth/login"
PASSWORD = "ngựa vằn ăn cỏ buổi sáng"
WRONG = "không phải mật khẩu này"


def new_email() -> str:
    return f"login-{uuid.uuid4().hex[:12]}@example.com"


def make_user(session: Session, *, verified: bool = True, password: str = PASSWORD) -> User:
    user = UserRepository(session).create(new_email(), hash_password(password))
    if verified:
        user.email_verified_at = user.created_at
    session.flush()
    return user


def login(
    client: TestClient, email: str, password: str = PASSWORD, ip: str | None = None
) -> tuple[int, dict[str, object]]:
    headers = {CLIENT_IP_HEADER: ip} if ip else {}
    response = client.post(LOGIN, json={"email": email, "password": password}, headers=headers)
    return response.status_code, response.json()


def other_ip() -> str:
    return f"172.16.{random.randrange(256)}.{random.randrange(1, 255)}"


# --- Answers ----------------------------------------------------------------------------------


def test_login_returns_a_token_its_expiry_and_whether_the_email_is_verified(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    status, body = login(client, user.email)
    assert status == 200
    assert set(body) == {"token", "expires_at", "email_verified"}
    assert body["email_verified"] is True


def test_login_expires_at_is_the_absolute_end_so_the_cookie_never_outlives_the_session(
    client: TestClient, db_session: Session
) -> None:
    """ADR-0020 §1: web sets the cookie to end at `expires_at`; the sliding 30 days is renewed
    server-side, so the cookie must last until the 90-day cap, not the first idle deadline."""
    user = make_user(db_session)
    status, body = login(client, user.email)
    assert status == 200
    row = db_session.scalars(
        select(AuthSession).where(AuthSession.token_hash == hash_token(str(body["token"])))
    ).one()
    assert datetime.fromisoformat(str(body["expires_at"])) == row.created_at + SESSION_MAX


def test_ac5_login_wrong_password_and_unknown_email_get_the_same_answer(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    wrong_password = login(client, user.email, WRONG)
    unknown_email = login(client, new_email(), WRONG)
    assert wrong_password == unknown_email == (401, {"detail": "invalid_credentials"})


def test_ac5_login_unknown_email_runs_a_dummy_hash(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real = auth.dummy_verify

    def counting(password: str) -> bool:
        calls.append(password)
        return real(password)

    monkeypatch.setattr(auth, "dummy_verify", counting)
    login(client, new_email(), WRONG)
    assert calls == [WRONG]


@pytest.mark.parametrize("state", ["deleted", "google_only"])
def test_ac5_login_deleted_or_passwordless_account_gets_the_same_answer_and_work(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    user = make_user(db_session)
    if state == "deleted":
        user.deleted_at = user.created_at
    else:
        user.password_hash = None
    db_session.flush()
    calls: list[str] = []

    def counting(password: str) -> bool:
        calls.append(password)
        return False

    monkeypatch.setattr(auth, "dummy_verify", counting)

    assert login(client, user.email) == (401, {"detail": "invalid_credentials"})
    assert calls == [PASSWORD]


def test_ac2_login_works_for_unverified_account(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, verified=False)
    status, body = login(client, user.email)
    assert status == 200
    assert body["email_verified"] is False


def test_login_email_is_normalized(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    assert login(client, f"  {user.email.upper()} ")[0] == 200


# --- Token ------------------------------------------------------------------------------------


def test_ac8_session_token_is_32_bytes_and_only_its_hash_is_stored(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    _, body = login(client, user.email)
    token = str(body["token"])
    assert len(token) >= 43  # base64url of 32 bytes
    assert TOKEN_BYTES == 32
    rows = db_session.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all()
    assert [row.token_hash for row in rows] == [hash_token(token)]
    assert token not in {str(value) for row in rows for value in vars(row).values()}


def test_ac7_every_login_issues_a_new_token(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    first = login(client, user.email)[1]["token"]
    second = login(client, user.email)[1]["token"]
    assert first != second


# --- A reset racing a login (ADR-0021: every session ends at reset) -------------------------


@pytest.fixture
def committed_user(engine: Engine) -> Iterator[User]:
    """Visible to a second connection, unlike users made in `db_session`."""
    with Session(engine, expire_on_commit=False) as session:
        user = UserRepository(session).create(new_email(), hash_password(PASSWORD))
        user.email_verified_at = user.created_at
        session.commit()
    yield user
    with Session(engine) as session:
        session.execute(delete(User).where(User.id == user.id))
        session.commit()


NEW_PASSWORD = "trâu già gặm cỏ non chiều"


def reset_while_hashing(monkeypatch: pytest.MonkeyPatch, engine: Engine, user: User) -> None:
    """While the login checks the old password, the owner resets it on another connection."""
    check = auth.verify_password

    def check_then_reset(password_hash: str, password: str) -> bool:
        ok = check(password_hash, password)
        with Session(engine) as other:
            other.execute(
                update(User)
                .where(User.id == user.id)
                .values(password_hash=hash_password(NEW_PASSWORD))
            )
            AuthSessionRepository(other).revoke_all(user.id, datetime.now(UTC))
            other.commit()
        return ok

    monkeypatch.setattr(auth, "verify_password", check_then_reset)


def live_sessions(engine: Engine, user: User) -> list[AuthSession]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuthSession).where(
                    AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)
                )
            )
        )


def test_login_racing_a_reset_gets_no_session(
    committed_user: User,  # first: torn down after the client's transaction has rolled back
    client: TestClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_while_hashing(monkeypatch, engine, committed_user)
    assert login(client, committed_user.email) == (401, {"detail": "invalid_credentials"})
    assert live_sessions(engine, committed_user) == []


def test_login_racing_a_reset_never_rehashes_the_old_password_over_the_new(
    committed_user: User,  # first: torn down after the client's transaction has rolled back
    client: TestClient,
    db_session: Session,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_while_hashing(monkeypatch, engine, committed_user)
    monkeypatch.setattr(auth, "needs_rehash", lambda password_hash: True)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    login(client, committed_user.email)
    # What the login's transaction would commit (the test rolls it back afterwards).
    stored = db_session.scalar(select(User.password_hash).where(User.id == committed_user.id))
    assert stored is not None
    assert verify_password(stored, NEW_PASSWORD)


def test_rehash_on_login_when_params_old(client: TestClient, db_session: Session) -> None:
    password = "an old ascii passphrase here"
    user = make_user(db_session, password=password)
    old_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(password)
    user.password_hash = old_hash
    db_session.flush()
    assert needs_rehash(old_hash)

    assert login(client, user.email, password)[0] == 200
    db_session.refresh(user)
    new_hash = user.password_hash
    assert new_hash is not None
    assert not needs_rehash(new_hash)
    assert verify_password(new_hash, password)


# --- Lock after failures (ADR-0020 §2) ---------------------------------------------------------


def test_ac6_five_failures_per_email_and_ip_in_15_minutes_block_the_sixth_even_if_correct(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    assert [login(client, user.email, WRONG)[0] for _ in range(5)] == [401] * 5
    response = client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 429
    assert 0 < int(response.headers["Retry-After"]) <= 15 * 60


def test_ac6_unknown_email_failures_are_counted(client: TestClient) -> None:
    email = new_email()
    assert [login(client, email, WRONG)[0] for _ in range(6)] == [401] * 5 + [429]


def test_ac6_other_ip_is_not_locked_by_one_ips_failures(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    for _ in range(6):
        login(client, user.email, WRONG)
    assert login(client, user.email, ip=other_ip())[0] == 200


def test_ac6_twenty_failures_per_email_across_ips_block_any_ip(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    statuses = [login(client, user.email, WRONG, ip=other_ip())[0] for _ in range(20)]
    assert statuses == [401] * 20
    assert login(client, user.email, ip=other_ip())[0] == 429


def test_ac6_ip_is_trusted_only_with_web_token(client: TestClient) -> None:
    # Without web's token, a claimed IP is ignored: every request is the same peer.
    email = new_email()
    for _ in range(5):
        client.post(
            LOGIN,
            json={"email": email, "password": WRONG},
            headers={"X-Service-Token": "not-the-web-token", CLIENT_IP_HEADER: other_ip()},
        )
    response = client.post(
        LOGIN,
        json={"email": email, "password": WRONG},
        headers={"X-Service-Token": "not-the-web-token", CLIENT_IP_HEADER: other_ip()},
    )
    assert response.status_code == 429


def test_correct_login_does_not_reset_the_failure_counter(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    statuses = [login(client, user.email, WRONG)[0] for _ in range(4)]
    statuses.append(login(client, user.email)[0])
    statuses += [login(client, user.email, WRONG)[0] for _ in range(2)]
    # The correct one is refunded; the earlier four still count: the next failure is the 5th.
    assert statuses == [401, 401, 401, 401, 200, 401, 429]


def test_correct_login_refunds_its_own_attempt(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    assert [login(client, user.email)[0] for _ in range(8)] == [200] * 8


def test_concurrent_failures_are_counted_before_hashing(
    client: TestClient,
    db_session: Session,
    client_ip: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A burst of requests must not all pass a check before any of them is counted.
    user = make_user(db_session)
    pair = RateLimit(f"test-{uuid.uuid4().hex}", 1, auth.LOGIN_PER_EMAIL_IP.window)
    monkeypatch.setattr(auth, "LOGIN_PER_EMAIL_IP", pair)
    seen: list[bool] = []

    def verify_while_another_request_arrives(password_hash: str, password: str) -> bool:
        limiter = RateLimiter(get_redis())
        seen.append(limiter.hit(pair, auth.login_pair_key(user.email, client_ip)).allowed)
        return False

    monkeypatch.setattr(auth, "verify_password", verify_while_another_request_arrives)
    login(client, user.email, WRONG)
    assert seen == [False], "the attempt was not counted before the password was hashed"


def test_login_fails_closed_when_redis_is_down(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = make_user(db_session)
    dead = redis_from_url("redis://127.0.0.1:1/0", timeout=0.2)
    monkeypatch.setattr(rate_limit, "get_redis", lambda: dead)
    assert login(client, user.email)[0] == 503


# --- Security log (ADR-0013) ------------------------------------------------------------------


def security_lines(output: str) -> list[dict[str, object]]:
    lines = [json.loads(line) for line in output.splitlines() if line.strip()]
    return [line for line in lines if line.get("logger") == "core_api.security"]


def test_security_events_logged_without_password_or_token(
    client: TestClient, db_session: Session, log_output: Callable[[], str]
) -> None:
    user = make_user(db_session)
    login(client, user.email, WRONG)
    token = str(login(client, user.email)[1]["token"])
    for _ in range(5):
        login(client, user.email, WRONG)

    output = log_output()
    events = [line["event"] for line in security_lines(output)]
    assert events[:2] == ["login_failed", "login_success"]
    assert "login_blocked" in events
    for secret in (PASSWORD, WRONG, token, hash_token(token)):
        assert secret not in output


def test_security_log_masks_email_and_hashes_ip(
    client: TestClient, db_session: Session, client_ip: str, log_output: Callable[[], str]
) -> None:
    user = make_user(db_session)
    login(client, user.email, WRONG)
    [line] = security_lines(log_output())
    assert user.email not in json.dumps(line)
    assert client_ip not in json.dumps(line)
    assert line["ip_hash"] == hash_ip(client_ip)


def test_ip_hash_depends_on_the_secret_key() -> None:
    ip = "203.0.113.7"
    assert hash_ip(ip, b"k" * 32) != hash_ip(ip, b"j" * 32)
    assert hash_ip(ip, b"k" * 32) == hash_ip(ip, b"k" * 32)
    assert ip not in hash_ip(ip, b"k" * 32)
