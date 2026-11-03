"""T1.23 (part 2): `POST /v1/auth/register` with a username and an optional contact phone.

Rules under test: US-12 AC1 + D2 (username shape, case, taken -> 409), D4 (phone normalized,
shared between accounts), AC5 (an email that already has an account never shows, not even through
which usernames stay free: review P1), ADR-0013 (no phone or username in the logs).
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounts import fresh_username
from core_api.db.models import User
from core_api.domain.auth.passwords import hash_password
from core_api.repositories.user import EmailTakenError, UsernameTakenError, UserRepository
from core_api.security.rate_limit import RateLimiter, RateLimiterUnavailableError

REGISTER = "/v1/auth/register"
PASSWORD = "ngựa vằn ăn cỏ buổi sáng"
OWNER_PASSWORD = "mật khẩu của chủ thật"


def new_email() -> str:
    return f"reg-{uuid.uuid4().hex[:12]}@example.com"


def post(client: TestClient, **fields: object) -> tuple[int, dict[str, str]]:
    body = {"email": new_email(), "password": PASSWORD, "username": fresh_username(), **fields}
    response = client.post(REGISTER, json=body)
    return response.status_code, response.json()


def test_ac1_register_stores_the_username_lowercase_and_the_phone_as_e164(
    client: TestClient, db_session: Session
) -> None:
    email = new_email()
    assert post(client, email=email, username="  Bob.Smith ", phone="0912 345 678")[0] == 202
    user = UserRepository(db_session).get_by_email(email)
    assert user is not None
    assert (user.username, user.phone) == ("bob.smith", "+84912345678")


def test_d4_the_phone_is_optional(client: TestClient, db_session: Session) -> None:
    email = new_email()
    assert post(client, email=email)[0] == 202
    user = UserRepository(db_session).get_by_email(email)
    assert user is not None and user.phone is None


def test_d4_two_accounts_can_share_a_phone(client: TestClient, db_session: Session) -> None:
    assert post(client, phone="0912345678")[0] == 202
    assert post(client, phone="+84912345678")[0] == 202
    phones = db_session.scalars(select(User.phone).where(User.phone == "+84912345678")).all()
    assert len(phones) == 2


@pytest.mark.parametrize("phone", ["12345", "0212345678", "+85912345678", "abc"])
def test_d4_a_bad_phone_is_refused_and_creates_nothing(
    client: TestClient, db_session: Session, phone: str
) -> None:
    email = new_email()
    assert post(client, email=email, phone=phone) == (422, {"detail": "phone_invalid"})
    assert UserRepository(db_session).get_by_email(email) is None


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("ab", "username_invalid"),
        ("a" * 21, "username_invalid"),
        ("1abc", "username_invalid"),
        ("12345", "username_invalid"),
        ("a@b", "username_invalid"),
        ("a..b", "username_invalid"),
        ("Ab c", "username_invalid"),
        ("admin", "username_reserved"),
        ("Support", "username_reserved"),
    ],
)
def test_d2_a_bad_username_is_refused_with_its_reason_and_creates_nothing(
    client: TestClient, db_session: Session, name: str, reason: str
) -> None:
    email = new_email()
    assert post(client, email=email, username=name) == (422, {"detail": reason})
    assert UserRepository(db_session).get_by_email(email) is None


def test_d2_the_username_is_required(client: TestClient) -> None:
    response = client.post(REGISTER, json={"email": new_email(), "password": PASSWORD})
    assert response.status_code == 422


def test_d2_a_taken_username_is_409_whatever_the_case(
    client: TestClient, db_session: Session
) -> None:
    # Red when: uniqueness is case-sensitive, or the 409 is not shown.
    name = fresh_username()
    assert post(client, username=name)[0] == 202
    assert post(client, username=name.upper()) == (409, {"detail": "username_taken"})
    assert db_session.scalars(select(User.id).where(User.username == name)).one()


def test_ac5_a_taken_email_with_a_free_username_answers_like_a_new_email(
    client: TestClient, db_session: Session
) -> None:
    owner = UserRepository(db_session).create(new_email(), hash_password(OWNER_PASSWORD))
    db_session.flush()
    taken = post(client, email=owner.email)
    fresh = post(client)
    assert taken == fresh == (202, {"status": "check_email"})


def test_ac5_a_taken_email_does_not_overwrite_the_owners_username_or_phone(
    client: TestClient, db_session: Session
) -> None:
    owner = UserRepository(db_session).create(
        new_email(), hash_password(OWNER_PASSWORD), phone="+84912345678"
    )
    db_session.flush()
    before = (owner.username, owner.phone, owner.password_hash)
    assert post(client, email=owner.email, phone="0988888888")[0] == 202
    db_session.refresh(owner)
    assert (owner.username, owner.phone, owner.password_hash) == before


def test_ac5_a_taken_email_still_holds_the_username_it_asked_for(
    client: TestClient, db_session: Session
) -> None:
    # Review P1. Red when: the username asked with an existing email stays free, so a probe can ask
    # again with another email and read from 202/409 whether the first email has an account.
    owner = UserRepository(db_session).create(new_email(), hash_password(OWNER_PASSWORD))
    db_session.flush()
    probe = fresh_username()
    assert post(client, email=owner.email, username=probe)[0] == 202
    assert post(client, username=probe) == (409, {"detail": "username_taken"})


def test_ac5_a_new_email_and_a_taken_email_leave_the_username_taken_the_same_way(
    client: TestClient, db_session: Session
) -> None:
    owner = UserRepository(db_session).create(new_email(), hash_password(OWNER_PASSWORD))
    db_session.flush()
    for email in (owner.email, new_email()):
        name = fresh_username()
        assert post(client, email=email, username=name)[0] == 202
        assert post(client, username=name)[0] == 409


def test_d2_losing_a_race_for_a_username_is_409_not_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both requests passed the free-name check; the second INSERT meets the unique index.
    name = fresh_username()
    assert post(client, username=name)[0] == 202

    def never_taken(self: UserRepository, username: str) -> bool:
        return False

    monkeypatch.setattr(UserRepository, "username_taken", never_taken)
    assert post(client, username=name) == (409, {"detail": "username_taken"})


@pytest.mark.parametrize("method", ["is_reserved", "reserve"])
def test_ac5_a_failing_username_hold_refuses_instead_of_letting_the_name_through(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    # Red when: the hold swallows a Redis error (fail open), which would free the name again.
    def broken(self: RateLimiter, *args: object) -> bool:
        raise RateLimiterUnavailableError

    owner = UserRepository(db_session).create(new_email(), hash_password(OWNER_PASSWORD))
    db_session.flush()
    monkeypatch.setattr(RateLimiter, method, broken)
    email = owner.email if method == "reserve" else new_email()
    body = {"email": email, "password": PASSWORD, "username": fresh_username()}
    assert client.post(REGISTER, json=body).status_code == 503


def test_repository_tells_apart_which_constraint_was_broken(db_session: Session) -> None:
    users = UserRepository(db_session)
    first = users.create(new_email(), username="same_name")
    db_session.flush()
    with pytest.raises(UsernameTakenError):
        users.create(new_email(), username="same_name")
    with pytest.raises(EmailTakenError):
        users.create(first.email, username="other_name")
    # Neither "taken": a name the database refuses is a bug of the caller, not a clash.
    with pytest.raises(IntegrityError):
        users.create(new_email(), username="Bob")
    with pytest.raises(IntegrityError):
        users.create(new_email(), username="a..b")


def test_repository_makes_a_name_from_the_email_and_avoids_clashes(db_session: Session) -> None:
    users = UserRepository(db_session)
    local = f"zed{uuid.uuid4().hex[:8]}"
    one = users.create(f"{local}@a.vn")
    two = users.create(f"{local}@b.vn")
    assert (one.username, two.username) == (local, f"{local}_2")


def test_adr0013_neither_the_phone_nor_the_username_reaches_the_logs(
    client: TestClient, log_output: Callable[[], str]
) -> None:
    name = "secretname" + uuid.uuid4().hex[:6]
    assert post(client, username=name, phone="0912345678")[0] == 202
    assert post(client, username=name, phone="0912345678")[0] == 409
    output = log_output()
    for secret in (name, "912345678", "0912345678"):
        assert secret not in output
