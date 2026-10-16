"""Base repository: every query on user data is scoped to one user (ARCH §6.2).

This is the main guard against one user reading another's data until row-level security
arrives (M6). A repository cannot be built without a `user_id`, and every query it makes
filters on it. Subclasses add queries through `_select()`, never `select(Model)` directly.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from core_api.db.base import UserOwned


class UserScopedRepository[M: UserOwned]:
    model: type[M]

    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        if not isinstance(user_id, uuid.UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("user_id must be a UUID")
        self.session = session
        self.user_id = user_id

    def _select(self) -> Select[tuple[M]]:
        """The only way to start a query: already filtered to this user."""
        return select(self.model).where(self.model.user_id == self.user_id)

    def get(self, id: uuid.UUID) -> M | None:
        return self.session.scalars(self._select().where(self.model.id == id)).one_or_none()

    def list(self) -> Sequence[M]:
        return self.session.scalars(self._select()).all()

    def add(self, obj: M) -> M:
        obj.user_id = self.user_id  # the owner is the repository's user, never the caller's
        self.session.add(obj)
        return obj

    def delete(self, id: uuid.UUID) -> bool:
        obj = self.get(id)
        if obj is None:
            return False
        self.session.delete(obj)
        return True
