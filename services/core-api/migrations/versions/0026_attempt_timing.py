"""attempt_timing

Group 3 of the v2 data model (ARCH §6.2, ADR-0008: additions only): how long a practice answer
took (PLAN T8.4). `served_at` is written by the server when the question is shown; the other
three come with the submit, in the same UPDATE that makes the attempt submitted, and are frozen
after it (attempt_guard, ADR-0024, is not changed). All four are NULL for review attempts and for
anything not measured. The downgrade drops the columns, and the timing with them.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-01 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKS = {
    "hidden_ms_not_negative": "hidden_ms >= 0",
    "active_ms_not_negative": "active_ms >= 0",
    "timing_ok_with_active_ms": "(active_ms IS NULL) = (timing_ok IS NULL)",
    "active_ms_needs_served_and_hidden": (
        "active_ms IS NULL OR (served_at IS NOT NULL AND hidden_ms IS NOT NULL)"
    ),
    "timing_when_submitted": "active_ms IS NULL OR status = 'submitted'",
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("attempt", sa.Column("served_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("attempt", sa.Column("hidden_ms", sa.Integer(), nullable=True))
    op.add_column("attempt", sa.Column("active_ms", sa.Integer(), nullable=True))
    op.add_column("attempt", sa.Column("timing_ok", sa.Boolean(), nullable=True))
    for name, sql in CHECKS.items():
        op.create_check_constraint(op.f(f"ck_attempt_{name}"), "attempt", sql)


def downgrade() -> None:
    """Downgrade schema."""
    for name in CHECKS:
        op.drop_constraint(op.f(f"ck_attempt_{name}"), "attempt", type_="check")
    for column in ("timing_ok", "active_ms", "hidden_ms", "served_at"):
        op.drop_column("attempt", column)
