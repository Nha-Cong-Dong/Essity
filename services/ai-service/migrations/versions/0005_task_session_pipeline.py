"""allow the tasks chunk_units and generate_questions in pipeline_run and llm_call (T4.16b)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-29 09:00:00.000000

Downgrade only works while no row has task `chunk_units` or `generate_questions`.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
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
    _set_tasks("'grade', 'extract_session', 'chunk_units', 'generate_questions'")


def downgrade() -> None:
    """Downgrade schema."""
    _set_tasks("'grade', 'extract_session'")
