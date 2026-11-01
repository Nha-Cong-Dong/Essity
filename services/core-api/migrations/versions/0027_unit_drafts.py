"""unit_drafts

Group 4 of the v2 data model (ARCH §6.2, ADR-0008: additions only), for T7.8: a session's draft
cards (`knowledge_unit.session_id`, `draft_key`), `retired_at`, `saved_at` and
`saved_learning_day`, the `study_ledger` table, `unit.saved.v1` in the outbox, and the retry
columns of `submission`. Old rows keep their shape. The downgrade refuses rather than delete
learner data or events.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-01 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out, not imported: a later change to the models must not change what this ran.
OLD_EVENTS = (
    "'document.uploaded.v1', 'grade.requested.v1', 'session.confirmed.v1',"
    " 'submission.created.v1', 'user.deleted.v1'"
)
NEW_EVENTS = (
    "'document.uploaded.v1', 'grade.requested.v1', 'session.confirmed.v1',"
    " 'submission.created.v1', 'unit.saved.v1', 'user.deleted.v1'"
)
UNIT_CHECKS = {
    "retired_at_only_when_retired": "retired_at IS NULL OR status = 'retired'",
    "saved_at_with_day": "(saved_at IS NULL) = (saved_learning_day IS NULL)",
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("knowledge_unit", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.add_column("knowledge_unit", sa.Column("draft_key", sa.String(length=64), nullable=True))
    op.add_column(
        "knowledge_unit", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "knowledge_unit", sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("knowledge_unit", sa.Column("saved_learning_day", sa.Date(), nullable=True))
    # SET NULL on the session column only: user_id stays (it is NOT NULL and the owner).
    op.create_foreign_key(
        op.f("fk_knowledge_unit_session_id_study_session"),
        "knowledge_unit",
        "study_session",
        ["session_id", "user_id"],
        ["id", "user_id"],
        ondelete="SET NULL (session_id)",
    )
    for name, sql in UNIT_CHECKS.items():
        op.create_check_constraint(op.f(f"ck_knowledge_unit_{name}"), "knowledge_unit", sql)
    op.create_index(
        "uq_knowledge_unit_session_draft_key",
        "knowledge_unit",
        ["session_id", "draft_key"],
        unique=True,
        postgresql_where=sa.text("draft_key IS NOT NULL"),
    )

    op.create_table(
        "study_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("learning_day", sa.Date(), nullable=False),
        # A plain UUID, as knowledge_unit.section_id: the ledger is history and outlives a section.
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.Column("units_saved", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "units_saved >= 0", name=op.f("ck_study_ledger_units_saved_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_session.id", "study_session.user_id"],
            name=op.f("fk_study_ledger_session_id_study_session"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subject.id", "subject.user_id"],
            name=op.f("fk_study_ledger_subject_id_subject"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_study_ledger_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_study_ledger")),
    )
    # A unique index, not a constraint: NULLS NOT DISTINCT so a row without a section is one value.
    op.create_index(
        "uq_study_ledger_session_day_section",
        "study_ledger",
        ["session_id", "learning_day", "section_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(op.f("ix_study_ledger_user_id"), "study_ledger", ["user_id"])
    op.create_index(
        "ix_study_ledger_user_id_learning_day", "study_ledger", ["user_id", "learning_day"]
    )

    op.drop_constraint(op.f("ck_outbox_event_type"), "outbox", type_="check")
    op.create_check_constraint(
        op.f("ck_outbox_event_type"), "outbox", f"event_type IN ({NEW_EVENTS})"
    )

    op.add_column(
        "submission",
        sa.Column("retry_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "submission", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_submission_retry_count_not_negative"), "submission", "retry_count >= 0"
    )


def _refuse_if(connection: sa.Connection, sql: str, what: str) -> None:
    held = connection.execute(sa.text(sql)).scalar_one()
    if held:
        raise RuntimeError(f"0027 downgrade: {held} {what}")


def downgrade() -> None:
    """Downgrade schema: refuses while any of the new data exists."""
    connection = op.get_bind()
    _refuse_if(connection, "SELECT count(*) FROM study_ledger", "study_ledger row(s)")
    _refuse_if(
        connection,
        "SELECT count(*) FROM knowledge_unit WHERE session_id IS NOT NULL OR draft_key IS NOT NULL"
        " OR retired_at IS NOT NULL OR saved_at IS NOT NULL",  # noqa: E501
        "knowledge_unit row(s) use the draft, retired or saved columns",
    )
    _refuse_if(
        connection,
        "SELECT count(*) FROM outbox WHERE event_type = 'unit.saved.v1'",
        "unit.saved.v1 event(s) in the outbox",
    )
    op.drop_constraint(op.f("ck_submission_retry_count_not_negative"), "submission", type_="check")
    op.drop_column("submission", "next_attempt_at")
    op.drop_column("submission", "retry_count")

    op.drop_constraint(op.f("ck_outbox_event_type"), "outbox", type_="check")
    op.create_check_constraint(
        op.f("ck_outbox_event_type"), "outbox", f"event_type IN ({OLD_EVENTS})"
    )

    op.drop_table("study_ledger")

    op.drop_index("uq_knowledge_unit_session_draft_key", table_name="knowledge_unit")
    for name in UNIT_CHECKS:
        op.drop_constraint(op.f(f"ck_knowledge_unit_{name}"), "knowledge_unit", type_="check")
    op.drop_constraint(
        op.f("fk_knowledge_unit_session_id_study_session"),
        "knowledge_unit",
        type_="foreignkey",
    )
    for column in ("saved_learning_day", "saved_at", "retired_at", "draft_key", "session_id"):
        op.drop_column("knowledge_unit", column)
