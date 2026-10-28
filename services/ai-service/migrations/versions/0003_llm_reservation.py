"""llm_reservation: money set aside for calls in flight (T2.11)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28 09:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "llm_reservation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_usd >= 0", name=op.f("ck_llm_reservation_amount_not_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_reservation")),
    )
    op.create_index(
        op.f("ix_llm_reservation_user_id_expires_at"),
        "llm_reservation",
        ["user_id", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_llm_reservation_user_id_expires_at"), table_name="llm_reservation")
    op.drop_table("llm_reservation")
