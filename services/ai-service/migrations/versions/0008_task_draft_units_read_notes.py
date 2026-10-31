"""allow the tasks draft_units and read_notes in pipeline_run and llm_call (T7.7)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-01 08:00:00.000000

Downgrade only works while no row has task `draft_units` or `read_notes`.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("pipeline_run", "llm_call")
_OLD = (
    "'grade', 'extract_session', 'chunk_units', 'generate_questions', 'parse_command',"
    " 'syllabus_toc'"
)


def _set_tasks(tasks: str) -> None:
    for table in _TABLES:
        name = f"ck_{table}_task_known"
        op.drop_constraint(op.f(name), table, type_="check")
        op.create_check_constraint(op.f(name), table, f"task IN ({tasks})")


def upgrade() -> None:
    """Upgrade schema."""
    _set_tasks(f"{_OLD}, 'draft_units', 'read_notes'")


def downgrade() -> None:
    """Downgrade schema."""
    _set_tasks(_OLD)
