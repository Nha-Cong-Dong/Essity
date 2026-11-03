"""Hackathon C7: the demo account has cards due today and practice questions ready."""

from sqlalchemy.orm import Session

from core_api.cli_demo_account import DEMO_EMAIL, DEMO_PASSWORD, seed_account
from core_api.domain.auth.passwords import verify_password
from core_api.repositories.today import TodayRepository
from core_api.repositories.user import UserRepository


def test_demo_account_has_due_cards_and_ready_practice(db_session: Session) -> None:
    seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)
    user = UserRepository(db_session).get_by_email(DEMO_EMAIL)
    assert user is not None
    assert user.email_verified_at is not None
    assert user.password_hash is not None and verify_password(user.password_hash, DEMO_PASSWORD)
    today = TodayRepository(db_session, user.id)
    assert len(today.scheduled_units()) == 4
    assert len(today.practice_candidates()) == 3  # the fourth waits for an unstudied section


def test_demo_account_runs_twice_without_adding(db_session: Session) -> None:
    seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)
    assert "already there" in seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)
