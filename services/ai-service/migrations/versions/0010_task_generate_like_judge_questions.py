"""allow the tasks generate_like, judge_questions (T9.6b)

For the generated practice questions (US-17): one call generates candidates, one judges them.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-02 09:00:00.000000

Downgrade only works while no row has one of the new tasks.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("pipeline_run", "llm_call")
_OLD = (
    "'grade', 'extract_session', 'chunk_units', 'generate_questions', 'parse_command',"
    " 'syllabus_toc', 'draft_units', 'read_notes', 'grade_practice', 'draft_answer',"
    " 'parse_question_bank'"
)
_NEW = "'generate_like', 'judge_questions'"


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
