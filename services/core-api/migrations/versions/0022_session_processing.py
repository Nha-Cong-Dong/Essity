"""session_processing

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-29 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "study_session"
CHECKS = {
    "processing_needs_confirmed": "processing_state IS NULL OR status = 'confirmed'",
    "processing_state_known": "processing_state IN ('failed', 'processed', 'processing')",
    "processing_step_known": (
        "processing_step IN ('anchoring', 'reading_notes', 'splitting_units', 'writing_questions')"
    ),
    "processing_reason_known": (
        "processing_reason IN ('internal_error', 'llm_unavailable', 'unreadable')"
    ),
    "processing_percent_range": (
        "processing_percent IS NULL OR processing_percent BETWEEN 0 AND 100"
    ),
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(TABLE, sa.Column("processing_state", sa.String(length=10), nullable=True))
    op.add_column(TABLE, sa.Column("processing_step", sa.String(length=17), nullable=True))
    op.add_column(TABLE, sa.Column("processing_percent", sa.SmallInteger(), nullable=True))
    op.add_column(TABLE, sa.Column("processing_reason", sa.String(length=16), nullable=True))
    for name, sql in CHECKS.items():
        op.create_check_constraint(op.f(f"ck_study_session_{name}"), TABLE, sql)


def downgrade() -> None:
    """Downgrade schema."""
    for name in CHECKS:
        op.drop_constraint(op.f(f"ck_study_session_{name}"), TABLE, type_="check")
    for column in (
        "processing_reason",
        "processing_percent",
        "processing_step",
        "processing_state",
    ):
        op.drop_column(TABLE, column)
