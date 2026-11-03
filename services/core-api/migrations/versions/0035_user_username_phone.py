"""user_username_phone

T1.23 (US-12 D1-D4, D6): `user.username` (required, lowercase, unique) and `user.phone`
(optional, contact only: not unique, not a login key). Existing accounts get a username made from
the part of their email before the `@` (`username_from_email`, written out here so a later change
to it cannot change what this ran), ordered by `created_at, id`; clashes get `_2`, `_3`. Nothing
is logged: names come from emails (ADR-0013).

Downgrade drops both columns, so a username a user chose is lost; upgrading again makes names
from emails. No server default: run this migration and start the new app together (an old app
cannot sign anyone up once `username` is NOT NULL).

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-03 21:40:00.000000

"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESERVED = frozenset(
    {
        "admin", "administrator", "root", "support", "essity", "api", "me", "help", "staff",
        "system", "moderator", "owner", "security", "postmaster", "noreply", "null", "undefined",
    }
)  # fmt: skip
FOREIGN = re.compile(r"[^a-z0-9_.]")
DOTS = re.compile(r"\.{2,}")


def make_username(email: str, taken: set[str]) -> str:
    local = email.strip().lower().rpartition("@")[0]
    base = FOREIGN.sub("", local).lstrip("0123456789_.")
    base = DOTS.sub(".", base)[:20] or "user"
    base = base.ljust(3, "_")
    if base not in RESERVED and base not in taken:
        return base
    counter = 2
    while True:
        suffix = f"_{counter}"
        candidate = base[: 20 - len(suffix)] + suffix
        if candidate not in RESERVED and candidate not in taken:
            return candidate
        counter += 1


def upgrade() -> None:
    op.add_column("user", sa.Column("username", sa.String(length=20), nullable=True))
    op.add_column("user", sa.Column("phone", sa.String(length=16), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text('SELECT id, email FROM "user" ORDER BY created_at, id')).all()
    taken: set[str] = set()
    for user_id, email in rows:
        name = make_username(email, taken)
        taken.add(name)
        connection.execute(
            sa.text('UPDATE "user" SET username = :name WHERE id = :id'),
            {"name": name, "id": user_id},
        )
    op.alter_column("user", "username", nullable=False)
    op.create_unique_constraint(op.f("uq_user_username"), "user", ["username"])
    op.create_check_constraint(
        "username_format",
        "user",
        "username = lower(username) AND username ~ '^[a-z][a-z0-9_.]{2,19}$'"
        " AND position('..' in username) = 0",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_user_username_format"), "user", type_="check")
    op.drop_constraint(op.f("uq_user_username"), "user", type_="unique")
    op.drop_column("user", "phone")
    op.drop_column("user", "username")
