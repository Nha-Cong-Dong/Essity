"""Request text that Postgres cannot store, or that has no place in an email address.

Postgres text cannot hold NUL, so an email carrying one reached the query and failed there.
Emails refuse every control character (after the surrounding whitespace that was always
accepted is stripped); passwords and tokens are only hashed, never stored, so they keep
taking any character (plan D4, D5). A login refused this way is a 422 that depends on the
shape of the text alone, never on whether an account exists (US-12 AC5).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.api import auth
from core_api.db.models import AuthSession, User
from core_api.domain.auth.passwords import hash_password
from core_api.repositories.user import UserRepository
from core_api.security.rate_limit import RateLimit, RateLimiter, RateLimitResult

PASSWORD = "ngựa vằn ăn cỏ buổi sáng"
# \x85 (NEL) is whitespace to the email pattern, so for the three paths that keep the pattern it
# was refused before the shared check; the other four test that check there.
CONTROL = ["\x00", "\x01", "\x1f", "\x7f", "\x85"]
EMAIL_PATHS = ["/v1/auth/register", "/v1/auth/verify-email/resend", "/v1/auth/password-reset"]


def new_email() -> str:
    return f"text-{uuid.uuid4().hex[:12]}@example.com"


def body_for(path: str, email: str) -> dict[str, str]:
    return {"email": email, "password": PASSWORD} if path.endswith("register") else {"email": email}


def post_raw(client: TestClient, path: str, raw: bytes) -> int:
    # httpx's json= cannot carry a lone surrogate; a hand-written escape can.
    response = client.post(path, content=raw, headers={"content-type": "application/json"})
    return response.status_code


# --- Emails -------------------------------------------------------------------------------------


@pytest.mark.parametrize("char", CONTROL)
def test_login_email_with_a_control_character_is_422_not_500(client: TestClient, char: str) -> None:
    email = f"a{char}{new_email()}"
    response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 422


@pytest.mark.parametrize("path", EMAIL_PATHS)
@pytest.mark.parametrize("char", CONTROL)
def test_email_with_a_control_character_is_422_not_500(
    client: TestClient, path: str, char: str
) -> None:
    response = client.post(path, json=body_for(path, f"a{char}{new_email()}"))
    assert response.status_code == 422


def test_login_email_with_a_control_character_is_not_counted_or_hashed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D8: refused before the rate limiter and argon2, as nothing was tried. Counted by calls,
    not by a later lock: the dirty email's limiter key differs from the clean one's."""
    hits: list[str] = []
    hashed: list[str] = []
    original = RateLimiter.hit

    def spy(self: RateLimiter, rule: RateLimit, key: str) -> RateLimitResult:
        hits.append(key)
        return original(self, rule, key)

    monkeypatch.setattr(RateLimiter, "hit", spy)
    monkeypatch.setattr(auth, "dummy_verify", hashed.append)
    email = f"a\x00{new_email()}"
    for _ in range(6):
        response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 422
    assert hits == []
    assert hashed == []


def test_422_for_an_unsafe_email_does_not_echo_it(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/login", json={"email": "secret\x00part@example.com", "password": PASSWORD}
    )
    assert response.status_code == 422
    assert "secret" not in response.text


@pytest.mark.parametrize("path", EMAIL_PATHS)
def test_email_with_surrounding_whitespace_is_still_accepted(client: TestClient, path: str) -> None:
    """Stripped as before: a trailing newline or tab from a paste is not a control character
    inside the address."""
    response = client.post(path, json=body_for(path, f" \t{new_email()}\n"))
    assert response.status_code == 202


def test_email_is_checked_as_it_is_stored(client: TestClient, db_session: Session) -> None:
    """Reviewer plan #3: Python's strip() drops \\x1c-\\x1f and \\x85 too, so a trailing one is
    accepted and stored without it, while the same character inside the address is a 422."""
    email = new_email()
    sent = {"email": f"{email}\x1f", "password": PASSWORD}
    assert client.post("/v1/auth/register", json=sent).status_code == 202
    assert db_session.scalars(select(User.email).where(User.email == email)).one() == email


def test_login_email_is_checked_as_it_is_stored(client: TestClient, db_session: Session) -> None:
    """Reviewer commit 393c02d #2: the address registered from "<email>\\x1f" signs in with it."""
    email = new_email()
    user = UserRepository(db_session).create(email, hash_password(PASSWORD))
    user.email_verified_at = user.created_at
    db_session.flush()
    response = client.post("/v1/auth/login", json={"email": f"{email}\x1f", "password": PASSWORD})
    assert response.status_code == 200


def test_login_with_surrounding_whitespace_still_signs_in(
    client: TestClient, db_session: Session
) -> None:
    email = new_email()
    user = UserRepository(db_session).create(email, hash_password(PASSWORD))
    user.email_verified_at = user.created_at
    db_session.flush()
    response = client.post("/v1/auth/login", json={"email": f" {email}\n", "password": PASSWORD})
    assert response.status_code == 200


def test_login_with_a_malformed_but_clean_email_is_still_401(client: TestClient) -> None:
    """D3: login keeps no email pattern, so a wrong-looking address answers like a wrong one."""
    response = client.post("/v1/auth/login", json={"email": "not-an-email", "password": PASSWORD})
    assert response.status_code == 401


# --- Lone surrogates (held by Pydantic only where a Field constraint encodes the text) ------------


@pytest.mark.parametrize(
    ("path", "raw"),
    [
        ("/v1/auth/login", b'{"email": "a\\ud800b@example.com", "password": "long enough one"}'),
        ("/v1/auth/login", b'{"email": "a@example.com", "password": "long \\ud800 enough"}'),
        ("/v1/auth/register", b'{"email": "a\\ud800b@example.com", "password": "long enough"}'),
        ("/v1/auth/register", b'{"email": "a@example.com", "password": "long \\ud800 enough"}'),
        ("/v1/auth/verify-email/resend", b'{"email": "a\\ud800b@example.com"}'),
        ("/v1/auth/password-reset", b'{"email": "a\\ud800b@example.com"}'),
        ("/v1/auth/verify-email", b'{"token": "ab\\ud800c"}'),
        ("/v1/auth/password-reset/confirm", b'{"token": "ab\\ud800c", "password": "long enough"}'),
        ("/v1/auth/password-reset/confirm", b'{"token": "abc", "password": "long \\ud800 one"}'),
    ],
)
def test_lone_surrogate_in_auth_text_is_422(client: TestClient, path: str, raw: bytes) -> None:
    assert post_raw(client, path, raw) == 422


# --- Passwords and tokens keep their characters (D4, D5) ------------------------------------------


def test_password_with_nul_is_accepted_at_register_and_login(
    client: TestClient, db_session: Session
) -> None:
    email, password = new_email(), "ngựa vằn\x00ăn cỏ buổi sáng"
    assert (
        client.post("/v1/auth/register", json={"email": email, "password": password}).status_code
        == 202
    )
    user = db_session.scalars(select(User).where(User.email == email)).one()
    user.email_verified_at = user.created_at
    db_session.flush()
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def test_token_with_nul_is_an_ordinary_bad_token(client: TestClient) -> None:
    response = client.post("/v1/auth/verify-email", json={"token": "ab\x00c"})
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid_or_expired_token"}


# --- Extra fields (D6) ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/auth/login", {"email": "a@example.com", "password": PASSWORD}),
        ("/v1/auth/register", {"email": "a@example.com", "password": PASSWORD}),
        ("/v1/auth/verify-email/resend", {"email": "a@example.com"}),
        ("/v1/auth/password-reset", {"email": "a@example.com"}),
        ("/v1/auth/verify-email", {"token": "abc"}),
        ("/v1/auth/password-reset/confirm", {"token": "abc", "password": PASSWORD}),
    ],
)
def test_auth_body_with_an_extra_field_is_422(
    client: TestClient, path: str, body: dict[str, str]
) -> None:
    if "email" in body:
        body = {**body, "email": new_email()}  # a fresh address: no cooldown 429 hides the 422
    response = client.post(path, json={**body, "is_admin": "true"})
    assert response.status_code == 422


# --- User-Agent (D7) ------------------------------------------------------------------------------


def test_user_agent_with_control_characters_is_stored_without_them(
    client: TestClient, db_session: Session
) -> None:
    """The HTTP server refuses such a header before the app; this guards a change of server."""
    email = new_email()
    user = UserRepository(db_session).create(email, hash_password(PASSWORD))
    user.email_verified_at = user.created_at
    db_session.flush()
    response = client.post(
        "/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"User-Agent": "Browser\x00/1.0\x01"},
    )
    assert response.status_code == 200
    stored = db_session.scalars(
        select(AuthSession.user_agent).where(AuthSession.user_id == user.id)
    )
    assert stored.one() == "Browser/1.0"
