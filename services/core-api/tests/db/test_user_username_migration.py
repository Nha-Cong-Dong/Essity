"""T1.23, migration 0035: existing accounts get a username from their email (D6), the database
refuses a name the rules refuse (D2), and downgrade then upgrade loses no account."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

# (email, expected username), in created_at order: the earlier one keeps the plain name.
CASES = [
    ("a.b@x.vn", "a.b"),
    ("9lives@x.vn", "lives"),
    ("ab@x.vn", "ab_"),
    ("a..b@x.vn", "a.b_2"),  # clashes with the first
    ("x+tag@x.vn", "xtag"),
    ("a" * 40 + "@x.vn", "a" * 20),
    ("admin@x.vn", "admin_2"),
    ("bob@a.vn", "bob"),
    ("bob@b.vn", "bob_2"),
    ("bob_2@c.vn", "bob_2_2"),  # `bob_2` is already taken by the line above
    ("@@x.vn", "user"),
    ("ünï@x.vn", "n__"),
]


def seed(engine: Engine) -> dict[str, str]:
    """Insert the accounts as 0034 left the table (no username column yet)."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ids: dict[str, str] = {}
    with engine.begin() as connection:
        for position, (email, _) in enumerate(CASES):
            user_id = str(uuid.uuid4())
            connection.execute(
                text(
                    'INSERT INTO "user" (id, email, created_at, password_hash)'
                    " VALUES (:id, :email, :created, 'kept-hash')"
                ),
                {"id": user_id, "email": email, "created": base + timedelta(minutes=position)},
            )
            ids[email] = user_id
    return ids


def test_0035_backfills_usernames_without_losing_accounts(
    engine: Engine, owner_engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: a name is illegal (bad character, bad first character, too short or long,
    # reserved), a clash is not resolved in created_at order, or an account loses data.
    ids: dict[str, str] = {}
    try:
        command.downgrade(alembic_cfg, "0034")
        ids = seed(owner_engine)
        command.upgrade(alembic_cfg, "0035")
        with owner_engine.connect() as connection:
            rows = {
                email: connection.execute(
                    text('SELECT username, display_name, password_hash FROM "user" WHERE id = :id'),
                    {"id": ids[email]},
                ).one()
                for email, _ in CASES
            }
        for email, expected in CASES:
            username, display_name, password_hash = rows[email]
            assert username == expected, email
            assert display_name is None and password_hash == "kept-hash"
    finally:
        command.upgrade(alembic_cfg, "head")
        with owner_engine.begin() as connection:
            connection.execute(
                text('DELETE FROM "user" WHERE id = ANY(:ids)'), {"ids": list(ids.values())}
            )


def test_0035_downgrade_then_upgrade_keeps_accounts(
    engine: Engine, owner_engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: the downgrade or the second upgrade deletes or rewrites an account.
    try:
        command.upgrade(alembic_cfg, "head")
        email = f"keep-{uuid.uuid4().hex[:8]}@example.com"
        with owner_engine.begin() as connection:
            connection.execute(
                text(
                    'INSERT INTO "user" (id, email, username, password_hash)'
                    " VALUES (gen_random_uuid(), :email, 'chosen_name', 'kept-hash')"
                ),
                {"email": email},
            )
        command.downgrade(alembic_cfg, "0034")
        command.upgrade(alembic_cfg, "0035")
        with owner_engine.connect() as connection:
            row = connection.execute(
                text('SELECT username, password_hash FROM "user" WHERE email = :email'),
                {"email": email},
            ).one()
        assert row.password_hash == "kept-hash"
        assert row.username == email.split("@")[0].replace("-", "")[:20]
    finally:
        with owner_engine.begin() as connection:
            connection.execute(
                text('DELETE FROM "user" WHERE username IS NOT NULL AND email LIKE :p'),
                {"p": "keep-%"},
            )
        command.upgrade(alembic_cfg, "head")


@pytest.mark.parametrize("name", ["Bob", "ab", "1abc", "a..b", "a b", "a@b", "x" * 21])
def test_d2_the_database_refuses_a_username_the_rules_refuse(
    owner_engine: Engine, name: str
) -> None:
    # Red when: the CHECK is missing or loosened (a path that skips the domain rules).
    with pytest.raises((IntegrityError, DBAPIError)), owner_engine.begin() as connection:
        connection.execute(
            text(
                'INSERT INTO "user" (id, email, username) VALUES (gen_random_uuid(), :email, :name)'
            ),
            {"email": f"chk-{uuid.uuid4().hex[:8]}@example.com", "name": name},
        )


def test_d2_the_database_refuses_two_accounts_with_one_username(owner_engine: Engine) -> None:
    name = f"dup{uuid.uuid4().hex[:8]}"
    insert = text(
        'INSERT INTO "user" (id, email, username) VALUES (gen_random_uuid(), :email, :name)'
    )
    try:
        with owner_engine.begin() as connection:
            connection.execute(insert, {"email": f"{name}-1@example.com", "name": name})
        with pytest.raises(IntegrityError), owner_engine.begin() as connection:
            connection.execute(insert, {"email": f"{name}-2@example.com", "name": name})
    finally:
        with owner_engine.begin() as connection:
            connection.execute(text('DELETE FROM "user" WHERE username = :name'), {"name": name})


def test_adr0024_core_app_writes_the_new_columns_and_the_eraser_deletes_the_row(
    engine: Engine, eraser_engine: Engine
) -> None:
    # Red when: the grants of 0034 did not reach the new columns.
    email = f"role-{uuid.uuid4().hex[:8]}@example.com"
    with engine.begin() as connection:
        user_id = connection.execute(
            text(
                'INSERT INTO "user" (id, email, username, display_name)'
                " VALUES (gen_random_uuid(), :email, :name, 'Ten Day Du') RETURNING id"
            ),
            {"email": email, "name": f"r{uuid.uuid4().hex[:10]}"},
        ).scalar_one()
    with eraser_engine.begin() as connection:
        deleted = connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": user_id})
    assert deleted.rowcount == 1
