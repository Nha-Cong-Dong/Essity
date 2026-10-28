"""allow the task extract_session in pipeline_run and llm_call (T4.10)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28 09:00:00.000000

PR #46 (T2.11) adds a migration 0003 too: whichever merges second renumbers this one to the next
free number and points `down_revision` at the other (alembic must show one head).
Downgrade only works while no row has task `extract_session`.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("pipeline_run", "llm_call")


def _set_tasks(tasks: str) -> None:
    for table in _TABLES:
        name = f"ck_{table}_task_known"
        op.drop_constraint(op.f(name), table, type_="check")
        op.create_check_constraint(op.f(name), table, f"task IN ({tasks})")


def upgrade() -> None:
    """Upgrade schema."""
    _set_tasks("'grade', 'extract_session'")


def downgrade() -> None:
    """Downgrade schema."""
    _set_tasks("'grade'")
