"""user subject exam

Revision ID: 0001
Revises:
Create Date: 2026-10-16 22:20:05.866005

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'Asia/Ho_Chi_Minh'"),
            nullable=False,
        ),
        sa.Column("day_start_hour", sa.SmallInteger(), server_default=sa.text("4"), nullable=False),
        sa.Column("fsrs_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fsrs_params_version", sa.Integer(), nullable=True),
        sa.Column("eval_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "day_start_hour BETWEEN 0 AND 23", name=op.f("ck_user_day_start_hour_range")
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_user_email_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
        sa.UniqueConstraint("email", name=op.f("uq_user_email")),
    )
    op.create_table(
        "subject",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_subject_name_not_blank")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_subject_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subject")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_subject_id_user_id")),
    )
    op.create_index(op.f("ix_subject_user_id"), "subject", ["user_id"], unique=False)
    op.create_table(
        "exam",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subject.id", "subject.user_id"],
            name=op.f("fk_exam_subject_id_subject"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_exam_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam")),
    )
    op.create_index(op.f("ix_exam_subject_id"), "exam", ["subject_id"], unique=False)
    op.create_index(op.f("ix_exam_user_id"), "exam", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_exam_user_id"), table_name="exam")
    op.drop_index(op.f("ix_exam_subject_id"), table_name="exam")
    op.drop_table("exam")
    op.drop_index(op.f("ix_subject_user_id"), table_name="subject")
    op.drop_table("subject")
    op.drop_table("user")
