"""T1.22, migration 0009: the baseline table and `user.baseline_skips` go, and come back exactly as
0005 made them (plan E1). The snapshot is taken from the real 0005, never written by hand."""

from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text

TABLES = ("baseline", "user")


def snapshot(connection: Connection) -> dict[str, Any]:
    """Columns, constraints and indexes of the two tables, by name (not by column order: a column
    added back sits last)."""
    # The full type, numeric(3,2) not numeric (review 097fdad #1), the NOT NULL and the default.
    columns = {
        (row.table, row.column): (row.type, row.not_null, row.default)
        for row in connection.execute(
            text(
                "SELECT c.relname AS table, a.attname AS column,"
                " format_type(a.atttypid, a.atttypmod) AS type, a.attnotnull AS not_null,"
                " pg_get_expr(d.adbin, d.adrelid) AS default"
                " FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid"
                " LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum"
                " WHERE c.relnamespace = 'public'::regnamespace AND c.relname = ANY(:tables)"
                " AND a.attnum > 0 AND NOT a.attisdropped"
            ),
            {"tables": list(TABLES)},
        )
    }
    constraints = {
        name: definition
        for name, definition in connection.execute(
            text(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conrelid IN (SELECT oid FROM pg_class WHERE relname = ANY(:tables)"
                " AND relnamespace = 'public'::regnamespace)"
            ),
            {"tables": list(TABLES)},
        )
    }
    indexes = {
        name: definition
        for name, definition in connection.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes"
                " WHERE schemaname = 'public' AND tablename = ANY(:tables)"
            ),
            {"tables": list(TABLES)},
        )
    }
    return {"columns": columns, "constraints": constraints, "indexes": indexes}


def take(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        return snapshot(connection)


def test_0009_drop_and_restore_match_0005(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: 0009's downgrade forgets a column, a CHECK, the cascade, the index or the user
    # column 0005 made, or its upgrade leaves the table or the column behind.
    try:
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "0008")
        made_by_0005 = take(engine)
        assert ("baseline", "gpa_before") in made_by_0005["columns"]
        assert ("user", "baseline_skips") in made_by_0005["columns"]
        assert "fk_baseline_user_id_user" in made_by_0005["constraints"]

        command.upgrade(alembic_cfg, "0009")
        dropped = take(engine)
        assert not any(table == "baseline" for table, _ in dropped["columns"])
        assert ("user", "baseline_skips") not in dropped["columns"]
        assert "ck_user_baseline_skips_range" not in dropped["constraints"]

        command.downgrade(alembic_cfg, "0008")
        assert take(engine) == made_by_0005
    finally:
        command.upgrade(alembic_cfg, "head")


@pytest.mark.parametrize(
    "change",
    [
        "ALTER TABLE baseline DROP CONSTRAINT ck_baseline_gpa_after_range",
        # numeric(4,2) and numeric(3,2) are both "numeric" in information_schema.data_type.
        "ALTER TABLE baseline ALTER COLUMN gpa_after TYPE numeric(4,2)",
        "ALTER TABLE baseline ALTER COLUMN is_late SET DEFAULT false",
    ],
)
def test_the_snapshot_sees_a_changed_schema(
    engine: Engine, alembic_cfg: Config, change: str
) -> None:
    # Red when: the snapshot leaves out a constraint, a column's full type or its default, so a
    # downgrade that got one wrong would pass (review 097fdad #1).
    try:
        command.downgrade(alembic_cfg, "0008")
        with engine.connect() as connection, connection.begin() as transaction:
            whole = snapshot(connection)
            connection.execute(text(change))
            assert snapshot(connection) != whole
            transaction.rollback()
    finally:
        command.upgrade(alembic_cfg, "head")
