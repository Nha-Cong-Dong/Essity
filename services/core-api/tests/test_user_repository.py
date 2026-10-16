import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.domain.email import normalize_email
from core_api.repositories.user import EmailTakenError, UserRepository


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("Alice@Example.COM", "alice@example.com"),
        ("  bob@example.com\n", "bob@example.com"),
        ("nguyen.van.a@gmail.com", "nguyen.van.a@gmail.com"),
    ],
)
def test_normalize_email(raw: str, normalized: str) -> None:
    assert normalize_email(raw) == normalized


def test_email_is_stored_normalized(db_session: Session) -> None:
    user = UserRepository(db_session).create("  Alice@Example.COM ")
    assert user.email == "alice@example.com"


def test_lookup_by_email_ignores_case_and_spaces(db_session: Session) -> None:
    users = UserRepository(db_session)
    alice = users.create("alice@example.com")
    db_session.flush()
    assert users.get_by_email("ALICE@example.com ") is alice


def test_same_email_in_another_case_is_taken(db_session: Session) -> None:
    users = UserRepository(db_session)
    users.create("alice@example.com")
    db_session.flush()
    with pytest.raises(EmailTakenError):
        users.create("ALICE@EXAMPLE.COM")
    # The session is still usable after the refusal.
    assert users.get_by_email("alice@example.com") is not None


def test_database_rejects_an_email_that_was_not_normalized(db_session: Session) -> None:
    # Last line of defence if some code path forgets normalize_email.
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("""INSERT INTO "user" (id, email) VALUES (gen_random_uuid(), 'A@x.com')""")
        )


def test_new_user_defaults(db_session: Session) -> None:
    user = UserRepository(db_session).create("alice@example.com")
    db_session.flush()
    db_session.refresh(user)
    assert user.timezone == "Asia/Ho_Chi_Minh"
    assert user.day_start_hour == 4
    assert user.email_verified_at is None
    assert user.password_hash is None  # allowed: Google-only accounts (M5)
    assert user.eval_consent_at is None
    assert user.fsrs_params is None
    assert user.deleted_at is None
    assert user.created_at is not None


def test_unknown_timezone_is_rejected(db_session: Session) -> None:
    with pytest.raises(ValueError):
        UserRepository(db_session).create("alice@example.com", timezone="Mars/Olympus")


@pytest.mark.parametrize("hour", [-1, 24])
def test_day_start_hour_out_of_range_is_rejected_by_the_database(
    db_session: Session, hour: int
) -> None:
    user = UserRepository(db_session).create("alice@example.com")
    db_session.flush()
    user.day_start_hour = hour
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_get_by_id(db_session: Session) -> None:
    users = UserRepository(db_session)
    alice = users.create("alice@example.com")
    db_session.flush()
    assert users.get(alice.id) is alice
