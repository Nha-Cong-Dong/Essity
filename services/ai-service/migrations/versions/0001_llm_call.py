"""pipeline_run and llm_call: the audit log of AI work (T2.10)

Revision ID: 0001
Revises:
Create Date: 2026-10-25 18:01:08.604188

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
        "pipeline_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("task", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("prompt_sha256", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="running", nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "prompt_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_pipeline_run_prompt_sha256_hex")
        ),
        sa.CheckConstraint(
            "status IN ('failed', 'running', 'succeeded')",
            name=op.f("ck_pipeline_run_status_known"),
        ),
        sa.CheckConstraint("task IN ('grade')", name=op.f("ck_pipeline_run_task_known")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_run")),
    )
    op.create_index(
        op.f("ix_pipeline_run_user_id_created_at"),
        "pipeline_run",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "llm_call",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("attempt", sa.SmallInteger(), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", sa.String(), nullable=True),
        sa.Column("stop_reason", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('anthropic', 'fake')", name=op.f("ck_llm_call_provider_known")
        ),
        sa.CheckConstraint("task IN ('grade')", name=op.f("ck_llm_call_task_known")),
        sa.CheckConstraint("attempt >= 1", name=op.f("ck_llm_call_attempt_positive")),
        sa.CheckConstraint("cost_usd >= 0", name=op.f("ck_llm_call_cost_not_negative")),
        sa.CheckConstraint("input_tokens >= 0", name=op.f("ck_llm_call_input_tokens_not_negative")),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_llm_call_latency_not_negative")),
        sa.CheckConstraint(
            "output_tokens >= 0", name=op.f("ck_llm_call_output_tokens_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_run.id"],
            name=op.f("fk_llm_call_pipeline_run_id_pipeline_run"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_call")),
    )
    op.create_index(
        op.f("ix_llm_call_pipeline_run_id"), "llm_call", ["pipeline_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_llm_call_user_id_created_at"), "llm_call", ["user_id", "created_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_llm_call_user_id_created_at"), table_name="llm_call")
    op.drop_index(op.f("ix_llm_call_pipeline_run_id"), table_name="llm_call")
    op.drop_table("llm_call")
    op.drop_index(op.f("ix_pipeline_run_user_id_created_at"), table_name="pipeline_run")
    op.drop_table("pipeline_run")
