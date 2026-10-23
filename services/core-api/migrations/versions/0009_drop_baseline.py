"""drop_baseline

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-23 22:00:00.000000

T1.22: US-11 was dropped on 23/10 (comparing study days and GPA put too much pressure on the
user), so its table and the skip counter on `user` go. There was no production database yet
(plan E8). The downgrade makes the schema of 0005 again, not its data: rows dropped here are gone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f("ck_user_baseline_skips_range"), "user", type_="check")
    op.drop_column("user", "baseline_skips")
    op.drop_index(op.f("ix_baseline_user_id"), table_name="baseline")
    op.drop_table("baseline")


def downgrade() -> None:
    """Downgrade schema: the upgrade of 0005, as it was."""
    op.create_table(
        "baseline",
        sa.Column("gpa_before", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("prior_ready_days", sa.SmallInteger(), nullable=False),
        sa.Column("prior_days_unknown", sa.Boolean(), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_late", sa.Boolean(), nullable=False),
        sa.Column("gpa_after", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "NOT prior_days_unknown OR prior_ready_days = 0",
            name=op.f("ck_baseline_unknown_days_are_zero"),
        ),
        sa.CheckConstraint("gpa_after BETWEEN 0 AND 4", name=op.f("ck_baseline_gpa_after_range")),
        sa.CheckConstraint("gpa_before BETWEEN 0 AND 4", name=op.f("ck_baseline_gpa_before_range")),
        sa.CheckConstraint(
            "prior_ready_days BETWEEN 0 AND 365", name=op.f("ck_baseline_prior_ready_days_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_baseline_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_baseline")),
        sa.UniqueConstraint("user_id", name=op.f("uq_baseline_user_id")),
    )
    op.create_index(op.f("ix_baseline_user_id"), "baseline", ["user_id"], unique=False)
    op.add_column(
        "user",
        sa.Column("baseline_skips", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_user_baseline_skips_range"), "user", "baseline_skips BETWEEN 0 AND 2"
    )
