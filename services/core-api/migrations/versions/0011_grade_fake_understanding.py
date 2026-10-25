"""grade_fake_understanding

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-25 21:00:00.000000

T2.13: the fake grader's grades are stored as source 'fake' (R41: never mistaken for a real
grade), and understanding is 1..3, the scale ai-service answers with (PR B decision B1). A row
with understanding 0 makes this migration fail loudly rather than being changed silently.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_OLD = "source IN ('ai', 'system', 'user_override')"
SOURCE_NEW = "source IN ('ai', 'fake', 'system', 'user_override')"
UNDERSTANDING = (
    "understanding IS NULL OR (overall NOT IN ('incorrect', 'forgot')"
    " AND understanding BETWEEN {low} AND 3)"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_grade_source_known"), "grade", type_="check")
    op.create_check_constraint("source_known", "grade", SOURCE_NEW)
    op.drop_constraint(op.f("ck_grade_understanding_when_right"), "grade", type_="check")
    op.create_check_constraint("understanding_when_right", "grade", UNDERSTANDING.format(low=1))


def downgrade() -> None:
    op.drop_constraint(op.f("ck_grade_understanding_when_right"), "grade", type_="check")
    op.create_check_constraint("understanding_when_right", "grade", UNDERSTANDING.format(low=0))
    op.drop_constraint(op.f("ck_grade_source_known"), "grade", type_="check")
    op.create_check_constraint("source_known", "grade", SOURCE_OLD)
