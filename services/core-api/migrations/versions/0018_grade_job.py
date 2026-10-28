"""grade job

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-28 10:00:00.000000

T4.19 (ADR-0006): an attempt whose grading went to the queue. `queued` until a grade exists,
`failed` with a code when the result can never be a grade. One row per attempt; it goes with the
attempt.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grade_job",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("failure", sa.String(length=12), nullable=True),
        sa.Column("request_key", sa.String(length=1024), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('failed', 'queued')", name=op.f("ck_grade_job_status_known")
        ),
        sa.CheckConstraint(
            "failure IS NULL OR failure IN ('disabled', 'invalid', 'unavailable')",
            name=op.f("ck_grade_job_failure_known"),
        ),
        sa.CheckConstraint(
            "(status = 'failed') = (failure IS NOT NULL)",
            name=op.f("ck_grade_job_failed_iff_failure"),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id", "user_id"],
            ["attempt.id", "attempt.user_id"],
            name=op.f("fk_grade_job_attempt_id_attempt"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_grade_job_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grade_job")),
        sa.UniqueConstraint("attempt_id", name=op.f("uq_grade_job_attempt_id")),
    )
    op.create_index(op.f("ix_grade_job_user_id"), "grade_job", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_grade_job_user_id"), table_name="grade_job")
    op.drop_table("grade_job")
