"""T1.7 (part 2): email verification tokens and `POST /v1/auth/verify-email`.

Rules under test, each named in its test: US-12 AC2 (one-time link, 24 hours), ADR-0014 (the
database keeps only the SHA-256 of a token), ADR-0019 §1 (every unexpired link works until the
email is verified, then none does).
"""

import hashlib
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from core_api.db.models import EmailToken, User
from core_api.domain.auth.tokens import TokenPurpose
from core_api.repositories.email_token import EmailTokenRepository
from core_api.repositories.user import UserRepository

VERIFY = "/v1/auth/verify-email"


@pytest.fixture
def user(two_users: tuple[User, User]) -> User:
    return two_users[0]


@pytest.fixture
def tokens(db_session: Session) -> EmailTokenRepository:
    return EmailTokenRepository(db_session)


def verify(client: TestClient, raw: str) -> int:
    return client.post(VERIFY, json={"token": raw}).status_code


def test_ac2_a_valid_link_verifies_the_email(
    client: TestClient, user: User, tokens: EmailTokenRepository, db_session: Session
) -> None:
    raw = tokens.issue(user.id, TokenPurpose.VERIFY_EMAIL)
    assert verify(client, raw) == 200
    db_session.refresh(user)
    assert user.email_verified_at is not None


def test_ac2_a_link_works_only_once(
    client: TestClient, user: User, tokens: EmailTokenRepository
) -> None:
    raw = tokens.issue(user.id, TokenPurpose.VERIFY_EMAIL)
    assert verify(client, raw) == 200
    assert verify(client, raw) == 400


def test_ac2_a_link_expires_after_24_hours(
    client: TestClient, user: User, tokens: EmailTokenRepository
) -> None:
    now = datetime.now(UTC)
    still_valid = tokens.issue(
        user.id, TokenPurpose.VERIFY_EMAIL, now=now - timedelta(hours=23, minutes=59)
    )
    expired = tokens.issue(
        user.id, TokenPurpose.VERIFY_EMAIL, now=now - timedelta(hours=24, seconds=1)
    )
    assert verify(client, expired) == 400
    assert verify(client, still_valid) == 200


def test_unknown_used_and_expired_links_get_the_same_answer(
    client: TestClient, user: User, tokens: EmailTokenRepository
) -> None:
    used = tokens.issue(user.id, TokenPurpose.VERIFY_EMAIL)
    verify(client, used)
    expired = tokens.issue(
        user.id, TokenPurpose.VERIFY_EMAIL, now=datetime.now(UTC) - timedelta(days=2)
    )
    reset = tokens.issue(user.id, TokenPurpose.RESET_PASSWORD)
    answers = {
        (response.status_code, response.text)
        for response in (
            client.post(VERIFY, json={"token": raw})
            for raw in (used, expired, reset, "no-such-token")
        )
    }
    assert len(answers) == 1  # nothing tells which case it was


def test_adr0019_an_older_unused_link_still_works(
    client: TestClient, user: User, tokens: EmailTokenRepository
) -> None:
    first = tokens.issue(user.id, TokenPurpose.VERIFY_EMAIL)
    tokens.issue(user.id, TokenPurpose.VERIFY_EMAIL)  # "Gửi lại"
    assert verify(client, first) == 200


def test_adr0019_verifying_ends_every_other_verification_link(
    client: TestClient, user: User, tokens: EmailTokenRepository
) -> None:
    first = tokens.issue(user.id, TokenPurpose.VERIFY_EMAIL)
    second = tokens.issue(user.id, TokenPurpose.VERIFY_EMAIL)
    assert verify(client, second) == 200
    assert verify(client, first) == 400


def test_a_password_reset_token_cannot_verify_an_email(
    client: TestClient, user: User, tokens: EmailTokenRepository, db_session: Session
) -> None:
    raw = tokens.issue(user.id, TokenPurpose.RESET_PASSWORD)
    assert verify(client, raw) == 400
    db_session.refresh(user)
    assert user.email_verified_at is None


def test_a_link_verifies_its_own_user_only(
    client: TestClient,
    two_users: tuple[User, User],
    tokens: EmailTokenRepository,
    db_session: Session,
) -> None:
    alice, bob = two_users
    assert verify(client, tokens.issue(alice.id, TokenPurpose.VERIFY_EMAIL)) == 200
    db_session.refresh(bob)
    assert bob.email_verified_at is None


def test_adr0014_the_database_keeps_only_the_hash(
    user: User, tokens: EmailTokenRepository, db_session: Session
) -> None:
    raw = tokens.issue(user.id, TokenPurpose.VERIFY_EMAIL)
    db_session.flush()
    [row] = db_session.scalars(select(EmailToken).where(EmailToken.user_id == user.id)).all()
    assert row.token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in {str(value) for value in vars(row).values()}


def test_the_token_travels_in_the_body_and_a_malformed_body_is_refused(
    client: TestClient,
) -> None:
    assert client.post(VERIFY).status_code == 422
    assert client.post(VERIFY, json={"token": "x" * 500}).status_code == 422


def test_a_deleted_account_cannot_be_verified(
    client: TestClient, user: User, tokens: EmailTokenRepository, db_session: Session
) -> None:
    raw = tokens.issue(user.id, TokenPurpose.VERIFY_EMAIL)
    user.deleted_at = datetime.now(UTC)
    db_session.flush()
    assert verify(client, raw) == 400
    db_session.refresh(user)
    assert user.email_verified_at is None


def test_the_same_link_clicked_twice_at_once_verifies_once(engine: Engine) -> None:
    # Real commits on two connections: the second click must wait for the first, then find
    # the token used.
    with Session(engine, expire_on_commit=False) as setup:
        owner = UserRepository(setup).create(f"race-{uuid.uuid4().hex[:12]}@example.com")
        setup.flush()
        raw = EmailTokenRepository(setup).issue(owner.id, TokenPurpose.VERIFY_EMAIL)
        setup.commit()
    try:
        first = Session(engine)
        assert EmailTokenRepository(first).consume(raw, TokenPurpose.VERIFY_EMAIL) == owner.id
        results: list[uuid.UUID | None] = []

        def second_click() -> None:
            with Session(engine) as second:
                results.append(EmailTokenRepository(second).consume(raw, TokenPurpose.VERIFY_EMAIL))
                second.commit()

        thread = threading.Thread(target=second_click)
        thread.start()
        thread.join(timeout=0.5)
        assert thread.is_alive(), "the second click did not wait for the first"
        first.commit()
        first.close()
        thread.join(timeout=5)
        assert results == [None]
    finally:
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": owner.id})
