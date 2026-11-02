"""unit_edge_deactivate_on_replace

T9.9 (US-19): a card that is merged or retired (a split makes its original `merged`) has been
replaced, so every active edge that touches it turns `inactive`, by whatever code path changes
the card. The edge is kept for the history; the learner's `rejected` edges stay as they are.
Hard deletion of a card already removes its edges (foreign key CASCADE, 0025). Additions only.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-02 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTION = """
CREATE FUNCTION knowledge_unit_deactivate_edges() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE unit_edge SET status = 'inactive'
   WHERE status IN ('active', 'proposed')
     AND (src_unit_id = NEW.id OR dst_unit_id = NEW.id);
  RETURN NULL;
END
$$
"""
TRIGGER = """
CREATE TRIGGER knowledge_unit_deactivate_edges
  AFTER UPDATE OF status ON knowledge_unit
  FOR EACH ROW
  WHEN (NEW.status IN ('merged', 'retired') AND OLD.status IS DISTINCT FROM NEW.status)
  EXECUTE FUNCTION knowledge_unit_deactivate_edges()
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(FUNCTION)
    op.execute(TRIGGER)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER knowledge_unit_deactivate_edges ON knowledge_unit")
    op.execute("DROP FUNCTION knowledge_unit_deactivate_edges()")
