"""Isolation check for every repository of user data (T1.3).

Every table holding a user's data gets a test calling `assert_isolated`: whatever user A
creates, user B cannot read, list, delete or take it over. B's repository never returns A's
row, and refuses A's row when B's code holds it anyway (an object passed along in the same
session).
"""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.orm import Session

from core_api.db.base import OwnerChangeError, UserOwned
from core_api.db.models import User
from core_api.repositories.base import UserScopedRepository


def assert_isolated[R: UserScopedRepository[Any]](
    session: Session,
    repository: type[R],
    owner: User,
    other: User,
    create: Callable[[R], UserOwned],
) -> None:
    mine = create(repository(session, owner.id))
    session.flush()
    theirs = repository(session, other.id)

    assert theirs.get(mine.id) is None, "B read A's row"
    assert mine.id not in {row.id for row in theirs.list()}, "B listed A's row"
    assert theirs.delete(mine.id) is False, "B deleted A's row"
    with pytest.raises(OwnerChangeError):
        theirs.add(mine)
    assert mine.user_id == owner.id, "B took over A's row"
    session.flush()
    assert repository(session, owner.id).get(mine.id) is not None, "A lost its own row"
