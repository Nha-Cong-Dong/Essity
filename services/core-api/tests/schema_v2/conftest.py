import pytest
from sqlalchemy.orm import Session

from core_api.db.models import User
from v2_rows import World, make_subject


@pytest.fixture
def world(db_session: Session, two_users: tuple[User, User]) -> World:
    alice, bob = two_users
    return World(
        db_session,
        alice,
        bob,
        make_subject(db_session, alice),
        make_subject(db_session, alice, "Cơ sở dữ liệu"),
    )
