"""command_log_v2

T9.2b (plan T9.2, ADR-0030): what applying and undoing a typed command needs in the database.
command_log gets the client's command_id (idempotency), the hash of the request and the revisions
the undo checks; doc_section and question get a `version` that a trigger raises on any change of
their content, by whatever code path; the removal of a practice question becomes an append-only
log (the schedule row is only a cache of it); a study filter gets its own table. Additions only:
the downgrade drops what this made and restores the 0025 guard.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-02 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out, not imported: a later change to the models must not change what this ran.
SECTION_CONTENT = (
    "title",
    "unit",
    "weight",
    "studied_weight",
    "excluded",
    "source",
    "first_page",
    "last_page",
    "parent_id",
    "ord",
)
QUESTION_CONTENT = (
    "level",
    "prompt",
    "reference_answer",
    "rubric",
    "status",
    "content_hash",
    "type_id",
    "answer_text",
    "answer_origin",
    "quality_status",
)


def _bump_function(table: str, columns: tuple[str, ...]) -> str:
    changed = "\n     OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in columns)
    return f"""
CREATE FUNCTION {table}_bump_version() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
  -- Whatever version the writer sent is ignored: only a change of content moves it, by one.
  IF {changed} THEN
    NEW.version := OLD.version + 1;
  ELSE
    NEW.version := OLD.version;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER {table}_bump_version BEFORE UPDATE ON {table}
  FOR EACH ROW EXECUTE FUNCTION {table}_bump_version();
"""


# The 0025 guard, as it was, for the downgrade.
GUARD_0025 = """
CREATE OR REPLACE FUNCTION command_log_guard() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
  IF OLD.status <> 'applied' OR NEW.status <> 'undone' OR NEW.undone_at IS NULL
     OR NEW.id <> OLD.id OR NEW.user_id <> OLD.user_id OR NEW.created_at <> OLD.created_at
     OR NEW.subject_id IS DISTINCT FROM OLD.subject_id
     OR NEW.screen_session_id IS DISTINCT FROM OLD.screen_session_id
     OR NEW.raw_text <> OLD.raw_text
     OR NEW.ops_json <> OLD.ops_json OR NEW.inverse_json <> OLD.inverse_json
     OR NEW.affected_count <> OLD.affected_count
     OR NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.seq <> OLD.seq THEN
    RAISE EXCEPTION 'UPDATE on command_log is refused: a command is only undone, once'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;
"""

# 0032: the same, and the new keys stay as written; `undo_revs_json` may be set once, by the
# undo, if the insert left it empty.
GUARD_0032 = """
CREATE OR REPLACE FUNCTION command_log_guard() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
  IF OLD.status <> 'applied' OR NEW.status <> 'undone' OR NEW.undone_at IS NULL
     OR NEW.id <> OLD.id OR NEW.user_id <> OLD.user_id OR NEW.created_at <> OLD.created_at
     OR NEW.subject_id IS DISTINCT FROM OLD.subject_id
     OR NEW.screen_session_id IS DISTINCT FROM OLD.screen_session_id
     OR NEW.raw_text <> OLD.raw_text
     OR NEW.ops_json <> OLD.ops_json OR NEW.inverse_json <> OLD.inverse_json
     OR NEW.affected_count <> OLD.affected_count
     OR NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.seq <> OLD.seq
     OR NEW.command_id <> OLD.command_id OR NEW.payload_hash <> OLD.payload_hash
     OR (OLD.undo_revs_json IS NOT NULL
         AND NEW.undo_revs_json IS DISTINCT FROM OLD.undo_revs_json) THEN
    RAISE EXCEPTION 'UPDATE on command_log is refused: a command is only undone, once'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;
"""

REMOVAL_GUARDS = """
CREATE TRIGGER practice_removal_log_append_only BEFORE UPDATE OR DELETE ON practice_removal_log
  FOR EACH ROW EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER practice_removal_log_no_truncate BEFORE TRUNCATE ON practice_removal_log
  FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse();
"""


def upgrade() -> None:
    """Upgrade schema."""
    # command_log. A default fills the old rows (the guard refuses an UPDATE), then goes.
    op.add_column(
        "command_log",
        sa.Column(
            "command_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
    )
    op.alter_column("command_log", "command_id", server_default=None)
    op.add_column(
        "command_log",
        sa.Column(
            "payload_hash",
            sa.CHAR(length=64),
            server_default=sa.text("repeat('0', 64)"),
            nullable=False,
        ),
    )
    op.alter_column("command_log", "payload_hash", server_default=None)
    op.add_column(
        "command_log",
        sa.Column("undo_revs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_command_log_payload_hash_hex"), "command_log", "payload_hash ~ '^[0-9a-f]{64}$'"
    )
    op.create_check_constraint(
        op.f("ck_command_log_undo_revs_is_object"),
        "command_log",
        "undo_revs_json IS NULL OR jsonb_typeof(undo_revs_json) = 'object'",
    )
    op.create_unique_constraint(
        op.f("uq_command_log_user_id_command_id"), "command_log", ["user_id", "command_id"]
    )
    op.create_index(
        "ix_command_log_user_id_screen_session_id_seq",
        "command_log",
        ["user_id", "screen_session_id", sa.text("seq DESC")],
    )
    op.execute(GUARD_0032)

    # doc_section / question: a version no code path can forget to raise.
    for table, columns in (("doc_section", SECTION_CONTENT), ("question", QUESTION_CONTENT)):
        op.add_column(table, sa.Column("version", sa.Integer(), server_default="1", nullable=False))
        op.create_check_constraint(op.f(f"ck_{table}_version_from_one"), table, "version >= 1")
        op.execute(_bump_function(table, columns))

    # practice_removal_log: the truth of "taken out of practice"; practice_state.removed_at is a
    # cache of the newest row. NO ACTION: a question with a history is never dropped.
    op.create_table(
        "practice_removal_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=7), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("command_id", sa.Uuid(), nullable=True),  # no foreign key: a button has none
        sa.CheckConstraint(
            "action IN ('readded', 'removed')", name=op.f("ck_practice_removal_log_action_known")
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "user_id"],
            ["question.id", "question.user_id"],
            name=op.f("fk_practice_removal_log_question_id_question"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_practice_removal_log_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_practice_removal_log")),
    )
    op.create_index(
        "ix_practice_removal_log_user_id_question_id_id",
        "practice_removal_log",
        ["user_id", "question_id", sa.text("id DESC")],
    )
    op.execute(REMOVAL_GUARDS)

    # study_filter: one row per user and subject; an undo clears `mode` and raises `rev`, never
    # deletes (a deleted row would let rev return to 1: ABA).
    op.create_table(
        "study_filter",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=5), nullable=True),
        sa.Column("until", sa.Date(), nullable=True),
        sa.Column("rev", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rev >= 1", name=op.f("ck_study_filter_rev_from_one")),
        sa.CheckConstraint("mode IN ('defer', 'only')", name=op.f("ck_study_filter_mode_known")),
        sa.ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subject.id", "subject.user_id"],
            name=op.f("fk_study_filter_subject_id_subject"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_study_filter_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "subject_id", name=op.f("pk_study_filter")),
    )


def downgrade() -> None:
    """Downgrade schema. The columns and tables made here go with their data."""
    op.drop_table("study_filter")
    op.drop_table("practice_removal_log")
    for table in ("question", "doc_section"):
        op.execute(f"DROP TRIGGER {table}_bump_version ON {table}")
        op.execute(f"DROP FUNCTION {table}_bump_version()")
        op.drop_constraint(op.f(f"ck_{table}_version_from_one"), table)
        op.drop_column(table, "version")
    op.execute(GUARD_0025)
    op.drop_index("ix_command_log_user_id_screen_session_id_seq", table_name="command_log")
    op.drop_constraint(op.f("uq_command_log_user_id_command_id"), "command_log")
    op.drop_constraint(op.f("ck_command_log_undo_revs_is_object"), "command_log")
    op.drop_constraint(op.f("ck_command_log_payload_hash_hex"), "command_log")
    op.drop_column("command_log", "undo_revs_json")
    op.drop_column("command_log", "payload_hash")
    op.drop_column("command_log", "command_id")
