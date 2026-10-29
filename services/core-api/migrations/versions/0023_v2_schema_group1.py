"""v2_schema_group1

Group 1 of the v2 data model (spec v2 §16.2, ADR-0008: additions only): document role and format,
the outline (doc_section), unit status/version/revisions, the question columns and types, the
section links and the submission. Old rows keep their shape; `question.level` stays (T5.R).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-30 03:35:44.171802

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_UNIT_STATUSES = "'active', 'merged', 'retired', 'split'"
NEW_UNIT_STATUSES = "'active', 'canonical', 'draft', 'merged', 'retired', 'split'"
CHECKS = {
    "document": {
        "role_known": "role IN ('auxiliary', 'question_bank', 'textbook')",
        "format_known": "format IN ('docx', 'image', 'pdf', 'pptx')",
    },
    "knowledge_unit": {"version_from_one": "version >= 1"},
    "question": {
        "source_known": "source IN ('bank', 'generated', 'review_auto')",
        "quality_status_known": "quality_status IN ('ok', 'pending', 'rejected')",
        "answer_origin_known": "answer_origin IN ('ai', 'bank', 'user')",
        "answer_text_with_origin": "(answer_text IS NULL) = (answer_origin IS NULL)",
        "unit_rev_not_negative": "unit_rev IS NULL OR unit_rev >= 0",
        "review_auto_has_run": "source <> 'review_auto' OR run_id IS NOT NULL",
    },
}


def upgrade() -> None:
    """Upgrade schema."""
    # First: doc_section's foreign key to document needs this key to exist.
    op.create_unique_constraint(
        op.f("uq_document_id_subject_id_user_id"), "document", ["id", "subject_id", "user_id"]
    )
    op.create_table(
        "question_type",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("ref_time_s", sa.Integer(), nullable=False),
        sa.Column("ref_origin", sa.String(length=14), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "name ~ '[^ \\t\\n\\v\\f\\r\\u0085\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]'",  # noqa: E501
            name=op.f("ck_question_type_name_not_blank"),
        ),
        sa.CheckConstraint(
            "ref_origin IN ('learner_median', 'rubric', 'user')",
            name=op.f("ck_question_type_ref_origin_known"),
        ),
        sa.CheckConstraint("ref_time_s > 0", name=op.f("ck_question_type_ref_time_positive")),
        sa.ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subject.id", "subject.user_id"],
            name=op.f("fk_question_type_subject_id_subject"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_question_type_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_type")),
        sa.UniqueConstraint(
            "id", "subject_id", "user_id", name=op.f("uq_question_type_id_subject_id_user_id")
        ),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_question_type_id_user_id")),
        sa.UniqueConstraint("subject_id", "name", name=op.f("uq_question_type_subject_id_name")),
    )
    op.create_index(op.f("ix_question_type_user_id"), "question_type", ["user_id"], unique=False)
    op.create_table(
        "doc_section",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1", nullable=False),
        sa.Column("unit", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("excluded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('bookmark', 'chunk10', 'heading', 'llm_toc', 'user')",
            name=op.f("ck_doc_section_source_known"),
        ),
        sa.CheckConstraint(
            "title ~ '[^ \\t\\n\\v\\f\\r\\u0085\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]'",  # noqa: E501
            name=op.f("ck_doc_section_title_not_blank"),
        ),
        sa.CheckConstraint(
            "unit IN ('est_page', 'page', 'slide')", name=op.f("ck_doc_section_unit_known")
        ),
        sa.CheckConstraint("ord >= 0", name=op.f("ck_doc_section_ord_not_negative")),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_doc_section_not_its_own_parent")
        ),
        sa.CheckConstraint("weight >= 0", name=op.f("ck_doc_section_weight_not_negative")),
        sa.ForeignKeyConstraint(
            ["document_id", "subject_id", "user_id"],
            ["document.id", "document.subject_id", "document.user_id"],
            name=op.f("fk_doc_section_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "document_id", "user_id"],
            ["doc_section.id", "doc_section.document_id", "doc_section.user_id"],
            name=op.f("fk_doc_section_parent_id_doc_section"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_doc_section_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doc_section")),
        sa.UniqueConstraint(
            "id", "document_id", "user_id", name=op.f("uq_doc_section_id_document_id_user_id")
        ),
        sa.UniqueConstraint(
            "id", "subject_id", "user_id", name=op.f("uq_doc_section_id_subject_id_user_id")
        ),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_doc_section_id_user_id")),
    )
    op.create_index(
        op.f("ix_doc_section_document_id_parent_id_ord"),
        "doc_section",
        ["document_id", "parent_id", "ord"],
        unique=False,
    )
    op.create_index(op.f("ix_doc_section_user_id"), "doc_section", ["user_id"], unique=False)
    op.create_table(
        "submission",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column(
            "file_keys",
            postgresql.ARRAY(sa.String(length=1024)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status IN ('done', 'failed')) = (finished_at IS NOT NULL)",
            name=op.f("ck_submission_finished_iff_ended"),
        ),
        sa.CheckConstraint(
            "status IN ('done', 'failed', 'pending_ai', 'processing', 'queued')",
            name=op.f("ck_submission_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_session.id", "study_session.user_id"],
            name=op.f("fk_submission_session_id_study_session"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_submission_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_submission_id_user_id")),
    )
    op.create_index(op.f("ix_submission_session_id"), "submission", ["session_id"], unique=False)
    op.create_index(op.f("ix_submission_user_id"), "submission", ["user_id"], unique=False)
    op.create_index(
        "ix_submission_waiting",
        "submission",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('queued', 'pending_ai')"),
    )
    op.create_table(
        "unit_revision",
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("rev", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=4), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(content) = 'object'", name=op.f("ck_unit_revision_content_is_object")
        ),
        sa.CheckConstraint("origin IN ('ai', 'user')", name=op.f("ck_unit_revision_origin_known")),
        sa.CheckConstraint("rev >= 0", name=op.f("ck_unit_revision_rev_not_negative")),
        sa.ForeignKeyConstraint(
            ["unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            name=op.f("fk_unit_revision_unit_id_knowledge_unit"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_unit_revision_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_revision")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_unit_revision_id_user_id")),
        sa.UniqueConstraint("unit_id", "rev", name=op.f("uq_unit_revision_unit_id_rev")),
    )
    op.create_index(op.f("ix_unit_revision_user_id"), "unit_revision", ["user_id"], unique=False)
    op.create_table(
        "question_section",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "subject_id", "user_id"],
            ["question.id", "question.subject_id", "question.user_id"],
            name=op.f("fk_question_section_question_id_question"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "subject_id", "user_id"],
            ["doc_section.id", "doc_section.subject_id", "doc_section.user_id"],
            name=op.f("fk_question_section_section_id_doc_section"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_question_section_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_section")),
        sa.UniqueConstraint(
            "question_id", "section_id", name=op.f("uq_question_section_question_id_section_id")
        ),
    )
    op.create_index(
        op.f("ix_question_section_section_id"), "question_section", ["section_id"], unique=False
    )
    op.create_index(
        op.f("ix_question_section_user_id"), "question_section", ["user_id"], unique=False
    )
    op.create_table(
        "unit_section",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "subject_id", "user_id"],
            ["doc_section.id", "doc_section.subject_id", "doc_section.user_id"],
            name=op.f("fk_unit_section_section_id_doc_section"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id", "subject_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.subject_id", "knowledge_unit.user_id"],
            name=op.f("fk_unit_section_unit_id_knowledge_unit"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_unit_section_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_section")),
        sa.UniqueConstraint(
            "unit_id", "section_id", name=op.f("uq_unit_section_unit_id_section_id")
        ),
    )
    op.create_index(
        op.f("ix_unit_section_section_id"), "unit_section", ["section_id"], unique=False
    )
    op.create_index(op.f("ix_unit_section_user_id"), "unit_section", ["user_id"], unique=False)
    op.add_column(
        "document",
        sa.Column("role", sa.String(length=14), server_default="auxiliary", nullable=False),
    )
    op.add_column(
        "document", sa.Column("format", sa.String(length=5), server_default="pdf", nullable=False)
    )
    op.create_index(
        "uq_document_textbook_per_subject",
        "document",
        ["subject_id"],
        unique=True,
        postgresql_where=sa.text("role = 'textbook'"),
    )
    op.add_column(
        "knowledge_unit", sa.Column("version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column(
        "question",
        sa.Column("source", sa.String(length=12), server_default="review_auto", nullable=False),
    )
    op.add_column("question", sa.Column("type_id", sa.Uuid(), nullable=True))
    op.add_column(
        "question",
        sa.Column("quality_status", sa.String(length=10), server_default="ok", nullable=False),
    )
    op.add_column("question", sa.Column("answer_text", sa.Text(), nullable=True))
    op.add_column("question", sa.Column("answer_origin", sa.String(length=4), nullable=True))
    op.add_column("question", sa.Column("kept_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("question", sa.Column("unit_rev", sa.Integer(), nullable=True))
    op.alter_column("question", "run_id", existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key(
        op.f("fk_question_type_id_question_type"),
        "question",
        "question_type",
        ["type_id", "subject_id", "user_id"],
        ["id", "subject_id", "user_id"],
    )
    op.drop_constraint(op.f("ck_knowledge_unit_status_known"), "knowledge_unit", type_="check")
    op.create_check_constraint(
        op.f("ck_knowledge_unit_status_known"),
        "knowledge_unit",
        f"status IN ({NEW_UNIT_STATUSES})",
    )
    for table, checks in CHECKS.items():
        for name, sql in checks.items():
            op.create_check_constraint(op.f(f"ck_{table}_{name}"), table, sql)


def downgrade() -> None:
    """Downgrade schema.

    Refuses, and changes nothing, while a row only the v2 schema can hold is left: a draft or
    canonical unit (the old check has neither) or a question without a run. Nothing is deleted or
    turned into something else to make the downgrade go through.
    """
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT 1 FROM knowledge_unit WHERE status IN ('draft', 'canonical') LIMIT 1")
    ).first():
        raise RuntimeError("0023 downgrade: units with status draft or canonical exist")
    if bind.execute(sa.text("SELECT 1 FROM question WHERE run_id IS NULL LIMIT 1")).first():
        raise RuntimeError("0023 downgrade: questions without a run_id exist")
    for table, checks in CHECKS.items():
        for name in checks:
            op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check")
    op.drop_constraint(op.f("ck_knowledge_unit_status_known"), "knowledge_unit", type_="check")
    op.create_check_constraint(
        op.f("ck_knowledge_unit_status_known"),
        "knowledge_unit",
        f"status IN ({OLD_UNIT_STATUSES})",
    )
    op.drop_constraint(op.f("fk_question_type_id_question_type"), "question", type_="foreignkey")
    op.alter_column("question", "run_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("question", "unit_rev")
    op.drop_column("question", "kept_at")
    op.drop_column("question", "answer_origin")
    op.drop_column("question", "answer_text")
    op.drop_column("question", "quality_status")
    op.drop_column("question", "type_id")
    op.drop_column("question", "source")
    op.drop_column("knowledge_unit", "version")
    op.drop_index(op.f("ix_unit_section_user_id"), table_name="unit_section")
    op.drop_index(op.f("ix_unit_section_section_id"), table_name="unit_section")
    op.drop_table("unit_section")
    op.drop_index(op.f("ix_question_section_user_id"), table_name="question_section")
    op.drop_index(op.f("ix_question_section_section_id"), table_name="question_section")
    op.drop_table("question_section")
    op.drop_index(op.f("ix_unit_revision_user_id"), table_name="unit_revision")
    op.drop_table("unit_revision")
    op.drop_index(
        "ix_submission_waiting",
        table_name="submission",
        postgresql_where=sa.text("status IN ('queued', 'pending_ai')"),
    )
    op.drop_index(op.f("ix_submission_user_id"), table_name="submission")
    op.drop_index(op.f("ix_submission_session_id"), table_name="submission")
    op.drop_table("submission")
    op.drop_index(op.f("ix_doc_section_user_id"), table_name="doc_section")
    op.drop_index(op.f("ix_doc_section_document_id_parent_id_ord"), table_name="doc_section")
    op.drop_table("doc_section")
    op.drop_index(op.f("ix_question_type_user_id"), table_name="question_type")
    op.drop_table("question_type")
    # After doc_section: its foreign key depends on this key.
    op.drop_index(
        "uq_document_textbook_per_subject",
        table_name="document",
        postgresql_where=sa.text("role = 'textbook'"),
    )
    op.drop_constraint(op.f("uq_document_id_subject_id_user_id"), "document", type_="unique")
    op.drop_column("document", "format")
    op.drop_column("document", "role")
