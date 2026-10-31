"""allow the tasks grade_practice, draft_answer, parse_question_bank (T7.M3)

For T8.4 (practice grading, drafted reference answers) and T8.1 (question-bank parsing); no call
site yet.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-01 09:30:00.000000

Downgrade only works while no row has one of the new tasks.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("pipeline_run", "llm_call")
_OLD = (
    "'grade', 'extract_session', 'chunk_units', 'generate_questions', 'parse_command',"
    " 'syllabus_toc', 'draft_units', 'read_notes'"
)
_NEW = "'grade_practice', 'draft_answer', 'parse_question_bank'"


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
