"""allow the tasks pick_sections and merge_drafts (CARDS-V3)

pick_sections: which sections of a mentioned document a vague @mention means; merge_drafts:
which drafts say the same thing. One call each per submission, at most.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-05 12:00:00.000000

Downgrade only works while no row has the new task.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("pipeline_run", "llm_call")
_OLD = (
    "'grade', 'extract_session', 'chunk_units', 'generate_questions', 'parse_command',"
    " 'syllabus_toc', 'draft_units', 'read_notes', 'grade_practice', 'draft_answer',"
    " 'parse_question_bank', 'generate_like', 'judge_questions', 'propose_edges'"
)
_NEW = "'pick_sections', 'merge_drafts'"


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
