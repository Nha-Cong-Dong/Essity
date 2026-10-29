"""unit_lineage

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-29 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("knowledge_unit", sa.Column("section_id", sa.Uuid(), nullable=True))
    op.add_column("anchor", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_anchor_document_id"), "anchor", ["document_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_anchor_document_id_document"),
        "anchor",
        "document",
        ["document_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        op.f("ck_anchor_notes_have_no_document"),
        "anchor",
        "source = 'document' OR document_id IS NULL",
    )
    op.create_table(
        "unit_lineage",
        sa.Column("old_unit_id", sa.Uuid(), nullable=False),
        sa.Column("new_unit_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.REAL(), nullable=True),  # pyright: ignore[reportUnknownArgumentType]
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_unit_lineage_confidence_unit"),
        ),
        sa.CheckConstraint(
            "old_unit_id <> new_unit_id", name=op.f("ck_unit_lineage_old_is_not_new")
        ),
        sa.ForeignKeyConstraint(
            ["new_unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            name=op.f("fk_unit_lineage_new_unit_id_knowledge_unit"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["old_unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            name=op.f("fk_unit_lineage_old_unit_id_knowledge_unit"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_unit_lineage_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_lineage")),
        sa.UniqueConstraint(
            "old_unit_id", "new_unit_id", name=op.f("uq_unit_lineage_old_unit_id_new_unit_id")
        ),
    )
    op.create_index(
        op.f("ix_unit_lineage_new_unit_id"), "unit_lineage", ["new_unit_id"], unique=False
    )
    op.create_index(
        op.f("ix_unit_lineage_old_unit_id"), "unit_lineage", ["old_unit_id"], unique=False
    )
    op.create_index(op.f("ix_unit_lineage_user_id"), "unit_lineage", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("unit_lineage")
    op.drop_constraint(op.f("ck_anchor_notes_have_no_document"), "anchor", type_="check")
    op.drop_constraint(op.f("fk_anchor_document_id_document"), "anchor", type_="foreignkey")
    op.drop_index(op.f("ix_anchor_document_id"), table_name="anchor")
    op.drop_column("anchor", "document_id")
    op.drop_column("knowledge_unit", "section_id")
