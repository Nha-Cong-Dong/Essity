"""allow the task propose_edges (T9.9)

For the edges between a saved card and other cards of its subject (US-19): one call per Save.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-02 12:00:00.000000

Downgrade only works while no row has the new task.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("pipeline_run", "llm_call")
_OLD = (
    "'grade', 'extract_session', 'chunk_units', 'generate_questions', 'parse_command',"
    " 'syllabus_toc', 'draft_units', 'read_notes', 'grade_practice', 'draft_answer',"
    " 'parse_question_bank', 'generate_like', 'judge_questions'"
)
_NEW = "'propose_edges'"


def _set_tasks(tasks: str) -> None:
    for table in _TABLES:
        name = f"ck_{table}_task_known"
        op.drop_constraint(op.f(name), table, type_="check")
        op.create_check_constraint(op.f(name), table, f"task IN ({tasks})")


def upgrade() -> None:
    """Upgrade schema."""
    _set_tasks(f"{_OLD}, {_NEW}")


def downgrade() -> None:
    """Downgrade schema."""
    _set_tasks(_OLD)
