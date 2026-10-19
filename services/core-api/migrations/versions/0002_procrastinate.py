"""procrastinate

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19 14:07:13.572042

The job queue's tables, types and functions (ADR-0014), from the Procrastinate schema frozen in
`migrations/sql/`. A later Procrastinate upgrade is a new migration running Procrastinate's own
migration SQL for that version, never `procrastinate schema --apply`.
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import LiteralString, cast

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = Path(__file__).parents[1] / "sql" / "procrastinate_3.10.0_schema.sql"


def upgrade() -> None:
    """Upgrade schema."""
    # Straight to psycopg, without parameters: SQLAlchemy would read `:name` as a bind parameter
    # and psycopg, once given parameters, `%` as a placeholder. Same transaction as Alembic's.
    psycopg_connection = op.get_bind().connection.driver_connection
    assert psycopg_connection is not None
    psycopg_connection.execute(cast(LiteralString, SCHEMA.read_text("utf-8")))


def downgrade() -> None:
    """Downgrade schema."""
    created = re.findall(r"^CREATE (TABLE|FUNCTION|TYPE) (\w+)", SCHEMA.read_text("utf-8"), re.M)
    # Functions first (CASCADE takes the triggers that call them), then the tables with their
    # indexes, then the types both used.
    for kind in ("FUNCTION", "TABLE", "TYPE"):
        names = [name for created_kind, name in created if created_kind == kind]
        cascade = " CASCADE" if kind == "FUNCTION" else ""
        for name in reversed(names):
            op.execute(f"DROP {kind} {name}{cascade}")
