"""Isolation check for every repository of user data (T1.3).

Every table holding a user's data gets a test calling `assert_isolated`: whatever user A
creates, user B cannot read, list or delete it. B cannot modify it either, because the only way
to obtain a row to modify is through B's own repository, which never returns it.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from core_api.db.base import UserOwned
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
    session.flush()
    assert repository(session, owner.id).get(mine.id) is not None, "A lost its own row"
