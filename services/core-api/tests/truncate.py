"""TRUNCATE of an append-only table, as the schema owner (T2.22).

`core_app` has no TRUNCATE privilege at all, so its attempts fail on the privilege and never reach
the trigger. The trigger is the second wall (a role granted TRUNCATE later still meets it), and it
is exercised here as the owner, on a connection of its own, with nothing in flight: TRUNCATE needs
an exclusive lock, which a test's own uncommitted rows would hold forever.
"""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError


def truncate_refused_by_trigger(owner_engine: Engine, tables: str) -> None:
    with pytest.raises(DBAPIError, match="is refused"), owner_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables}"))  # noqa: S608
