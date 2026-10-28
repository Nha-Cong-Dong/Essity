"""outbox

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-25 20:07:37.873746

T4.2 (ADR-0006): the transactional outbox. `user_id` has no foreign key to `user` on purpose
(plan E2): `user.deleted.v1` must outlive its user. `event_type` takes the core → ai events only
(plan G1). The partial index is what the relay reads: unsent rows, due first, then by `seq`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trace_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('document.uploaded.v1', 'grade.requested.v1',"
            " 'session.confirmed.v1', 'user.deleted.v1')",
            name=op.f("ck_outbox_event_type"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_outbox_attempts_not_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
        sa.UniqueConstraint("seq", name=op.f("uq_outbox_seq")),
    )
    op.create_index(
        "ix_outbox_unsent",
        "outbox",
        ["available_at", "seq"],
        unique=False,
        postgresql_where=sa.text("sent_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_unsent", table_name="outbox", postgresql_where=sa.text("sent_at IS NULL")
    )
    op.drop_table("outbox")
