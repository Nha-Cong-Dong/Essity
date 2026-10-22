"""Edge cases the independent tester added for `text-field-validator` (each names the change that
turns it red)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.db.models import AuthSession, User
from core_api.domain.auth.passwords import hash_password
from core_api.repositories.user import UserRepository

PASSWORD = "ngựa vằn ăn cỏ buổi sáng"


def new_email() -> str:
    return f"edge-{uuid.uuid4().hex[:12]}@example.com"


def make_user(session: Session) -> User:
    user = UserRepository(session).create(new_email(), hash_password(PASSWORD))
    user.email_verified_at = user.created_at
    session.flush()
    return user


def stored_agents(session: Session, user: User) -> list[str | None]:
    return list(
        session.scalars(select(AuthSession.user_agent).where(AuthSession.user_id == user.id))
    )


def test_user_agent_is_cleaned_before_it_is_cut(client: TestClient, db_session: Session) -> None:
    """Catches: the cut to 256 done before the control characters are dropped (a header that
    starts with control characters would then keep fewer than 256 real characters)."""
    user = make_user(db_session)
    agent = "\x01" * 10 + "a" * 300
    response = client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
        headers={"User-Agent": agent},
    )
    assert response.status_code == 200
    assert stored_agents(db_session, user) == ["a" * 256]


def test_user_agent_of_only_control_characters_is_stored_as_null(
    client: TestClient, db_session: Session
) -> None:
    """Catches: `kept or None` replaced by `kept` (an empty string stored instead of NULL)."""
    user = make_user(db_session)
    response = client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
        headers={"User-Agent": "\x00\x01\x02"},
    )
    assert response.status_code == 200
    assert stored_agents(db_session, user) == [None]


def test_login_email_length_limit_is_320(client: TestClient) -> None:
    """Catches: `max_length` dropped or changed on `LoginEmail` (321 would reach the query)."""
    at_limit = "a" * (320 - len("@example.com")) + "@example.com"
    assert len(at_limit) == 320
    body = {"email": at_limit, "password": PASSWORD}
    assert client.post("/v1/auth/login", json=body).status_code == 401
    body = {"email": "a" + at_limit, "password": PASSWORD}
    assert client.post("/v1/auth/login", json=body).status_code == 422


@pytest.mark.parametrize("char", ["\u200b", "\u200d", "\ufeff"])
def test_register_email_with_a_format_character_is_not_refused_as_control(
    client: TestClient, char: str
) -> None:
    """Catches: the control check widened to category Cf at the route (only Cc is refused)."""
    response = client.post(
        "/v1/auth/register", json={"email": f"a{char}{new_email()}", "password": PASSWORD}
    )
    assert response.status_code == 202


def test_register_with_a_control_character_creates_no_user(
    client: TestClient, db_session: Session
) -> None:
    """Catches: the check moved after the insert (a refused sign-up would leave a row)."""
    prefix = f"edge-{uuid.uuid4().hex[:12]}"
    response = client.post(
        "/v1/auth/register", json={"email": f"{prefix}\x00@example.com", "password": PASSWORD}
    )
    assert response.status_code == 422
    assert db_session.scalars(select(User.id).where(User.email.like(f"{prefix}%"))).first() is None


def test_dirty_login_answers_the_same_for_a_real_and_an_unknown_account(
    client: TestClient, db_session: Session
) -> None:
    """US-12 AC5, D8: the 422 depends on the text alone. Catches: a check that runs after the
    user lookup (the real account would answer differently from an unknown one)."""
    user = make_user(db_session)
    real = client.post("/v1/auth/login", json={"email": user.email + "\x00", "password": PASSWORD})
    unknown = client.post(
        "/v1/auth/login", json={"email": new_email() + "\x00", "password": PASSWORD}
    )
    assert real.status_code == unknown.status_code == 422
    assert real.json() == unknown.json()
