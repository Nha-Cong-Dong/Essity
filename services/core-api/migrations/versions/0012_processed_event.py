"""processed_event

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-26 09:00:00.000000

T4.4 (ADR-0006): the events each consumer of core-api has handled, keyed by (consumer,
event_id), so an event delivered twice is handled once.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processed_event",
        sa.Column("consumer", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("consumer", "event_id", name=op.f("pk_processed_event")),
    )


def downgrade() -> None:
    op.drop_table("processed_event")
