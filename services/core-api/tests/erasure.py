"""Deleting test users the way production does (T2.22): through a `core_eraser` login.

Tests used to switch the append-only triggers off with the owner's rights to clean up; the app
role cannot, and nothing should. `DELETE FROM "user"` by a member of `core_eraser` cascades
through the history tables and is the one path the triggers let through.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import Engine, text


def erase_users(eraser_engine: Engine, user_ids: Iterable[uuid.UUID]) -> None:
    with eraser_engine.begin() as connection:
        for user_id in user_ids:
            connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": user_id})


def erase_user(eraser_engine: Engine, user_id: uuid.UUID) -> None:
    erase_users(eraser_engine, [user_id])
