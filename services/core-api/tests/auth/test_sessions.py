"""T1.8: sessions, `GET /v1/me`, `POST /v1/auth/logout` and `/logout-all`.

Rules under test, each named in its test: US-12 AC7 and ADR-0020 §1 (30 days sliding, 90 days at
most, logout revokes at once), ADR-0020 §3 (logout-all revokes every session of the user, the
current one too), AC10 (a token only ever reaches its own user), A1 (the token travels in
`Authorization: Bearer`), A15 (no secret header reaches a span).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.db.models import AuthSession, User
from core_api.domain.auth.passwords import hash_password
from core_api.domain.auth.sessions import SESSION_IDLE, SESSION_MAX, session_expiry
from core_api.domain.auth.tokens import hash_token
from core_api.repositories.user import UserRepository

PASSWORD = "ngựa vằn ăn cỏ buổi sáng"
ME = "/v1/me"
LOGOUT = "/v1/auth/logout"
LOGOUT_ALL = "/v1/auth/logout-all"


def make_user(session: Session) -> User:
    user = UserRepository(session).create(
        f"session-{uuid.uuid4().hex[:12]}@example.com", hash_password(PASSWORD)
    )
    user.email_verified_at = user.created_at
    session.flush()
    return user


def sign_in(client: TestClient, user: User) -> str:
    response = client.post("/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200
    return str(response.json()["token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def row(session: Session, token: str) -> AuthSession:
    found = session.scalars(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    ).one()
    session.refresh(found)
    return found


# --- Domain -----------------------------------------------------------------------------------


def test_session_expiry_slides_30_days_but_never_past_90() -> None:
    created = datetime(2026, 1, 1, tzinfo=UTC)
    assert SESSION_IDLE == timedelta(days=30)
    assert SESSION_MAX == timedelta(days=90)
    assert session_expiry(created, created) == created + timedelta(days=30)
    assert session_expiry(created, created + timedelta(days=50)) == created + timedelta(days=80)
    assert session_expiry(created, created + timedelta(days=70)) == created + timedelta(days=90)


# --- /v1/me -----------------------------------------------------------------------------------


def test_me_returns_the_signed_in_user(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    response = client.get(ME, headers=bearer(sign_in(client, user)))
    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "email": user.email,
        "email_verified": True,
        "timezone": user.timezone,
        "day_start_hour": user.day_start_hour,
    }


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-real-token"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer "},
    ],
)
def test_me_requires_a_valid_bearer_token(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get(ME, headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "not_authenticated"}


def test_me_never_returns_hash_or_token(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    token = sign_in(client, user)
    text = client.get(ME, headers=bearer(token)).text
    assert user.password_hash is not None
    for secret in (token, hash_token(token), user.password_hash, "fsrs", "consent"):
        assert secret not in text


def test_me_rejects_deleted_account(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    token = sign_in(client, user)
    user.deleted_at = datetime.now(UTC)
    db_session.flush()
    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_ac10_a_token_only_ever_reaches_its_own_user(
    client: TestClient, db_session: Session
) -> None:
    alice, bob = make_user(db_session), make_user(db_session)
    alice_token, bob_token = sign_in(client, alice), sign_in(client, bob)
    assert client.get(ME, headers=bearer(alice_token)).json()["id"] == str(alice.id)
    assert client.get(ME, headers=bearer(bob_token)).json()["id"] == str(bob.id)


# --- Expiry (AC7, ADR-0020 §1) ----------------------------------------------------------------


def test_ac7_session_expires_after_30_days_idle(client: TestClient, db_session: Session) -> None:
    token = sign_in(client, make_user(db_session))
    session_row = row(db_session, token)
    session_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_ac7_each_request_slides_the_expiry(client: TestClient, db_session: Session) -> None:
    token = sign_in(client, make_user(db_session))
    session_row = row(db_session, token)
    earlier = datetime.now(UTC) - timedelta(days=10)
    session_row.created_at, session_row.last_seen_at = earlier, earlier
    session_row.expires_at = earlier + SESSION_IDLE
    db_session.flush()

    assert client.get(ME, headers=bearer(token)).status_code == 200
    session_row = row(db_session, token)
    assert session_row.expires_at > earlier + SESSION_IDLE + timedelta(days=9)
    assert session_row.last_seen_at > earlier + timedelta(days=9)


def test_ac7_session_dies_at_90_days_absolute(client: TestClient, db_session: Session) -> None:
    token = sign_in(client, make_user(db_session))
    session_row = row(db_session, token)
    # Used every day: the sliding expiry is far ahead, but the session is 90 days old.
    session_row.created_at = datetime.now(UTC) - SESSION_MAX - timedelta(seconds=1)
    session_row.expires_at = datetime.now(UTC) + timedelta(days=29)
    db_session.flush()
    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_ac7_sliding_never_extends_past_90_days(client: TestClient, db_session: Session) -> None:
    token = sign_in(client, make_user(db_session))
    session_row = row(db_session, token)
    created = datetime.now(UTC) - timedelta(days=80)
    session_row.created_at = created
    db_session.flush()
    assert client.get(ME, headers=bearer(token)).status_code == 200
    assert row(db_session, token).expires_at <= created + SESSION_MAX


# --- Logout (AC7, ADR-0020 §3) ----------------------------------------------------------------


def test_ac7_logout_revokes_immediately(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    token, other = sign_in(client, user), sign_in(client, user)
    assert client.post(LOGOUT, headers=bearer(token)).status_code == 204
    assert client.get(ME, headers=bearer(token)).status_code == 401
    assert client.get(ME, headers=bearer(other)).status_code == 200, "only this session ends"


def test_logout_requires_a_session(client: TestClient) -> None:
    assert client.post(LOGOUT).status_code == 401


def test_logout_all_revokes_every_session_including_current(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    tokens = [sign_in(client, user) for _ in range(3)]
    assert client.post(LOGOUT_ALL, headers=bearer(tokens[0])).status_code == 204
    assert [client.get(ME, headers=bearer(t)).status_code for t in tokens] == [401] * 3


def test_logout_all_leaves_other_users_sessions(client: TestClient, db_session: Session) -> None:
    alice, bob = make_user(db_session), make_user(db_session)
    alice_token, bob_token = sign_in(client, alice), sign_in(client, bob)
    client.post(LOGOUT_ALL, headers=bearer(alice_token))
    assert client.get(ME, headers=bearer(bob_token)).status_code == 200
