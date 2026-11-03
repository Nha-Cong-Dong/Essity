"""session_piece

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-04 08:00:00.000000

F2 (04/11): a study session is made of pieces; each "Ghi lại" keeps one in this table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_piece",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "files", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            "mentions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_session_piece_position_from_zero")),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_session.id", "study_session.user_id"],
            name=op.f("fk_session_piece_session_id_study_session"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_session_piece_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_piece")),
        sa.UniqueConstraint(
            "session_id", "position", name=op.f("uq_session_piece_session_id_position")
        ),
    )
    op.create_index(op.f("ix_session_piece_user_id"), "session_piece", ["user_id"])


def downgrade() -> None:
    op.drop_table("session_piece")
