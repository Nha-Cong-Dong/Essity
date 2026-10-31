"""T7.M2, migration 0025, edge cases added by the tester (ADR-0008; ARCH §6.2; no user story,
so no AC). Each test kills a mutation of 0025 that the first suite let live."""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from core_api.db.models import CommandLog, PracticeState
from v2_rows import NOW, World, make_question, make_subject, make_unit


def add(world: World, row: Any) -> Any:
    world.session.add(row)
    world.session.flush()
    return row


def count(world: World, table: str, user: uuid.UUID) -> int:
    return world.session.execute(
        text(f"SELECT count(*) FROM {table} WHERE user_id = :u"),  # noqa: S608
        {"u": user},
    ).scalar_one()


def command(world: World, **kw: Any) -> CommandLog:
    values: dict[str, Any] = {
        "user_id": world.alice.id,
        "subject_id": world.subject.id,
        "screen_session_id": uuid.uuid4(),
        "run_id": uuid.uuid4(),
        "raw_text": "gộp hai thẻ",
        "ops_json": [{"op": "merge"}],
        "inverse_json": [{"op": "split"}],
        "status": "applied",
        "affected_count": 2,
    }
    values.update(kw)
    return CommandLog(**values)


# --- command_log guard: the undo may not carry any other change -------------------------------


@pytest.mark.parametrize(
    "change",
    [
        "ops_json = '[]'",
        "inverse_json = '[]'",
        "raw_text = 'khác'",
        "affected_count = 0",
        "subject_id = NULL",
        "screen_session_id = NULL",
        "run_id = NULL",
        "user_id = :bob",
        "id = gen_random_uuid()",
        "created_at = created_at - interval '1 day'",
        "seq = DEFAULT",
    ],
)
def test_command_log_undo_refused_when_it_changes_another_column(world: World, change: str) -> None:
    # Red when: command_log_guard leaves one column out of its comparison, so an undo can
    # rewrite what the command did, where it ran, or whose it is.
    row = add(world, command(world))
    with pytest.raises(DBAPIError, match="is refused"), world.session.begin_nested():
        world.session.execute(
            text(
                f"UPDATE command_log SET status = 'undone', undone_at = now(), {change}"  # noqa: S608
                " WHERE id = :id"
            ),
            {"id": row.id, "bob": world.bob.id},
        )


def test_command_log_zero_affected_accepted(world: World) -> None:
    # Red when: the CHECK is affected_count > 0 (a command that matched nothing is still logged).
    add(world, command(world, affected_count=0))


@pytest.mark.parametrize("raw_text", [" ", "　 ", "\t \n"])
def test_command_log_unicode_blank_text_refused(world: World, raw_text: str) -> None:
    # Red when: the not-blank CHECK knows ASCII spaces only.
    with pytest.raises(IntegrityError), world.session.begin_nested():
        add(world, command(world, raw_text=raw_text))


# --- practice_state keeps the question --------------------------------------------------------


def test_question_delete_blocked_while_it_has_a_practice_state(world: World) -> None:
    # Red when: the key practice_state -> question is ON DELETE CASCADE, so deleting a question
    # silently drops its practice schedule.
    question = make_question(world.session, world.alice, world.subject)
    add(
        world,
        PracticeState(
            user_id=world.alice.id,
            question_id=question.id,
            phase="review",
            stability=3.0,
            difficulty=5.0,
            due=NOW,
            last_review=NOW,
        ),
    )
    with pytest.raises(IntegrityError), world.session.begin_nested():
        world.session.execute(text("DELETE FROM question WHERE id = :id"), {"id": question.id})
    assert count(world, "practice_state", world.alice.id) == 1


# --- unit_edge --------------------------------------------------------------------------------


def insert_user_edge(world: World, src: uuid.UUID, dst: uuid.UUID) -> None:
    """Raw insert that leaves evidence out, as a user-made edge from T9.9 may."""
    world.session.execute(
        text(
            "INSERT INTO unit_edge (id, user_id, subject_id, src_unit_id, dst_unit_id, kind,"
            " origin, status) VALUES (gen_random_uuid(), :u, :s, :a, :b, 'part_of', 'user',"
            " 'active')"
        ),
        {"u": world.alice.id, "s": world.subject.id, "a": src, "b": dst},
    )


def test_unit_edge_evidence_defaults_to_empty_array(world: World) -> None:
    # Red when: evidence has no server default '[]', so a user edge must invent one.
    src = make_unit(world.session, world.alice, world.subject)
    dst = make_unit(world.session, world.alice, world.subject)
    insert_user_edge(world, src.id, dst.id)
    evidence = world.session.execute(
        text("SELECT evidence FROM unit_edge WHERE user_id = :u"), {"u": world.alice.id}
    ).scalar_one()
    assert evidence == []


def test_unit_edge_goes_with_its_source_unit(world: World) -> None:
    # Red when: the src key is not ON DELETE CASCADE (only the dst side was tested).
    src = make_unit(world.session, world.alice, world.subject)
    dst = make_unit(world.session, world.alice, world.subject)
    insert_user_edge(world, src.id, dst.id)
    world.session.execute(text("DELETE FROM knowledge_unit WHERE id = :id"), {"id": src.id})
    assert count(world, "unit_edge", world.alice.id) == 0


# --- Account deletion is not blocked by the new tables that are not history -------------------


def test_user_delete_takes_practice_state_edges_and_commands(world: World) -> None:
    # Red when: a user key of practice_state, unit_edge or command_log is not ON DELETE CASCADE,
    # so deleting an account without practice history is refused. Bob's rows stay.
    for user in (world.alice, world.bob):
        subject = world.subject if user is world.alice else make_subject(world.session, user)
        question = make_question(world.session, user, subject)
        add(
            world,
            PracticeState(
                user_id=user.id,
                question_id=question.id,
                phase="review",
                stability=3.0,
                difficulty=5.0,
                due=NOW,
                last_review=NOW,
            ),
        )
        src = make_unit(world.session, user, subject)
        dst = make_unit(world.session, user, subject)
        world.session.execute(
            text(
                "INSERT INTO unit_edge (id, user_id, subject_id, src_unit_id, dst_unit_id, kind,"
                " origin, status) VALUES (gen_random_uuid(), :u, :s, :a, :b, 'part_of', 'user',"
                " 'active')"
            ),
            {"u": user.id, "s": subject.id, "a": src.id, "b": dst.id},
        )
        add(world, command(world, user_id=user.id, subject_id=None))
    world.session.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": world.alice.id})
    for table in ("practice_state", "unit_edge", "command_log"):
        assert count(world, table, world.alice.id) == 0
        assert count(world, table, world.bob.id) == 1


# --- Partial indexes: alembic's compare does not look at WHERE --------------------------------


def test_partial_indexes_of_new_tables_match_the_models(world: World) -> None:
    # Red when: the migration or a model drops or changes the WHERE of a partial index (the
    # model comparison of test_migration_0025 is blind to postgresql_where).
    from core_api.db.base import Base

    tables = ("practice_state", "practice_log", "command_log", "unit_edge")
    in_models = {
        index.name: str(index.dialect_options["postgresql"]["where"])
        for table in tables
        for index in Base.metadata.tables[table].indexes
        if index.dialect_options["postgresql"]["where"] is not None
    }
    rows = world.session.execute(
        text(
            "SELECT indexname, pg_get_expr(i.indpred, i.indrelid) FROM pg_indexes p"
            " JOIN pg_class c ON c.relname = p.indexname"
            " JOIN pg_index i ON i.indexrelid = c.oid"
            " WHERE p.tablename = ANY(:t) AND i.indpred IS NOT NULL"
        ),
        {"t": list(tables)},
    ).all()
    in_db: dict[str, str] = {str(name): str(where).strip("()") for name, where in rows}
    assert in_models == {"ix_practice_state_user_id_due": "removed_at IS NULL"}
    assert in_db == in_models
