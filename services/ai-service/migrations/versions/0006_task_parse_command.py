"""allow the task parse_command in pipeline_run and llm_call (T9.1)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30 06:00:00.000000

Downgrade only works while no row has task `parse_command`.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
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
    _set_tasks("'grade', 'extract_session', 'chunk_units', 'generate_questions', 'parse_command'")


def downgrade() -> None:
    """Downgrade schema."""
    _set_tasks("'grade', 'extract_session', 'chunk_units', 'generate_questions'")
