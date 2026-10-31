import pytest
from sqlalchemy.orm import Session

from core_api.db.models import User
from practice_rows import Practice


@pytest.fixture
def practice(db_session: Session, two_users: tuple[User, User]) -> Practice:
    return Practice(db_session, two_users[0])


@pytest.fixture
def bobs(db_session: Session, two_users: tuple[User, User]) -> Practice:
    return Practice(db_session, two_users[1])
