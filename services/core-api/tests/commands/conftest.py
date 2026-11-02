import pytest
from cmd_world import CmdWorld
from sqlalchemy.orm import Session

from core_api.db.models import User


@pytest.fixture
def cw(db_session: Session, two_users: tuple[User, User]) -> CmdWorld:
    return CmdWorld(db_session, two_users[0])
