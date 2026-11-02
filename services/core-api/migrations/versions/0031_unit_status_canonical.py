"""knowledge_unit.status: active becomes canonical

For T7.11 (ADR-0008, v2): a saved card is `canonical`; `active` and `split` leave the CHECK. Old
`active` rows become `canonical`, `split` rows become `retired`. The old `knowledge_unit.section_id`
is copied into `unit_section` (only ids that still exist in `doc_section`); the column itself stays
(the Save flow still writes it).

Downgrade puts the 0023 CHECK back (it allows `canonical` too) and changes no data: a canonical row
stays canonical.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-02 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "ck_knowledge_unit_status_known"
OLD = "'active', 'canonical', 'draft', 'merged', 'retired', 'split'"
NEW = "'canonical', 'draft', 'merged', 'retired'"


def _swap(statuses: str) -> None:
    op.drop_constraint(op.f(CHECK), "knowledge_unit", type_="check")
    op.create_check_constraint(op.f(CHECK), "knowledge_unit", f"status IN ({statuses})")


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "UPDATE knowledge_unit SET status = 'retired', retired_at = COALESCE(retired_at, now())"
        " WHERE status = 'split'"
    )
    op.execute("UPDATE knowledge_unit SET status = 'canonical' WHERE status = 'active'")
    op.execute(
        "INSERT INTO unit_section (id, user_id, subject_id, unit_id, section_id)"
        " SELECT gen_random_uuid(), u.user_id, u.subject_id, u.id, u.section_id"
        " FROM knowledge_unit u JOIN doc_section s ON s.id = u.section_id"
        " AND s.subject_id = u.subject_id AND s.user_id = u.user_id"
        " WHERE u.section_id IS NOT NULL"
        " ON CONFLICT (unit_id, section_id) DO NOTHING"
    )
    _swap(NEW)


def downgrade() -> None:
    """Downgrade schema. Data stays as it is (canonical stays canonical)."""
    _swap(OLD)
