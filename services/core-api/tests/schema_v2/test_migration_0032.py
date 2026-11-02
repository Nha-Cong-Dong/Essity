"""T9.2b, migration 0032 (plan T9.2, ADR-0030, US-18 AC4/AC5/AC9): the command log keeps the
client's id and the request hash, doc_section and question carry a version a trigger raises, the
removal of a practice question is an append-only log the schedule cache is rebuilt from, and a
study filter has its own table. Each case is one wrong row or one missed bump."""

import uuid
from datetime import date
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from core_api.db.base import Base
from core_api.db.models import CommandLog, User
from core_api.db.models import PracticeState as PracticeStateRow
from core_api.repositories.command_log import CommandLogRepository
from core_api.repositories.practice import PracticeStateRepository
from core_api.repositories.practice_removal import PracticeRemovalRepository
from core_api.repositories.question import QuestionRepository
from core_api.repositories.study_filter import StudyFilterRepository
from core_api.services.outline import OutlineService
from practice_rows import Practice, day
from v2_rows import World, make_document, make_question, make_section, make_subject

HASH = "ab" * 32


@pytest.fixture
def practice(db_session: Session, two_users: tuple[User, User]) -> Practice:
    return Practice(db_session, two_users[0])


def test_single_alembic_head_is_0032(alembic_cfg: Config) -> None:
    # Red when: another migration branches from 0031, or 0032 is not the head.
    assert ScriptDirectory.from_config(alembic_cfg).get_heads() == ["0032"]


def refused_sql(world: World, sql: str, **params: Any) -> None:
    """Refused by a trigger itself (its message says 'refused')."""
    with pytest.raises(DBAPIError, match="refused"), world.session.begin_nested():
        world.session.execute(text(sql), params)


def refused(world: World, row: Any) -> None:
    with pytest.raises(IntegrityError), world.session.begin_nested():
        world.session.add(row)
        world.session.flush()


# --- command_log ------------------------------------------------------------------------------


def log_row(world: World, user: User | None = None, **kw: Any) -> CommandLog:
    repo = CommandLogRepository(world.session, (user or world.alice).id)
    values: dict[str, Any] = {
        "command_id": uuid.uuid4(),
        "payload_hash": HASH,
        "raw_text": "bỏ chương 3",
        "ops": [{"op": "section_exclude"}],
        "inverse": [{"op": "revert"}],
        "affected_count": 1,
        "screen_session_id": uuid.uuid4(),
    }
    values.update(kw)
    row = repo.add_new(**values)
    assert row is not None
    return row


def test_command_id_is_unique_per_user_not_across_users(world: World) -> None:
    # Red when: UNIQUE(command_id) alone (B's retry of A's id is refused, or A's id leaks), or the
    # key leaves user_id out and two of one user's commands share an id.
    shared = uuid.uuid4()
    first = log_row(world, command_id=shared)
    assert log_row(world, world.bob, command_id=shared).id != first.id
    again = CommandLogRepository(world.session, world.alice.id).add_new(
        command_id=shared,
        payload_hash=HASH,
        raw_text="x",
        ops=[],
        inverse=[],
        affected_count=0,
    )
    assert again is None  # ON CONFLICT DO NOTHING: the caller reads the stored row


def test_by_command_id_is_scoped_to_the_user(world: World) -> None:
    # Red when: by_command_id drops the user filter (B would receive A's diff).
    row = log_row(world)
    assert CommandLogRepository(world.session, world.alice.id).by_command_id(row.command_id)
    assert CommandLogRepository(world.session, world.bob.id).by_command_id(row.command_id) is None


def test_latest_open_is_newest_not_undone_of_the_session_and_user(world: World) -> None:
    # Red when: latest_open ignores the session, the status, the order or the user.
    session_id, other = uuid.uuid4(), uuid.uuid4()
    first = log_row(world, screen_session_id=session_id)
    second = log_row(world, screen_session_id=session_id)
    log_row(world, screen_session_id=other)
    log_row(world, world.bob, screen_session_id=session_id)
    repo = CommandLogRepository(world.session, world.alice.id)
    latest = repo.latest_open(session_id)
    assert latest is not None
    assert latest.command_id == second.command_id
    assert repo.mark_undone(second.command_id) is not None
    latest = repo.latest_open(session_id)
    assert latest is not None
    assert latest.command_id == first.command_id
    assert repo.latest_open(uuid.uuid4()) is None


def test_mark_undone_once_and_never_for_another_user(world: World) -> None:
    # Red when: a second mark flips again, another user's row is flipped, or undo_revs is lost.
    row = log_row(world)
    assert CommandLogRepository(world.session, world.bob.id).mark_undone(row.command_id) is None
    repo = CommandLogRepository(world.session, world.alice.id)
    done = repo.mark_undone(row.command_id, undo_revs={"section:x": 3})
    assert done is not None
    assert (done.status, done.undo_revs_json) == ("undone", {"section:x": 3})
    assert done.undone_at is not None
    assert repo.mark_undone(row.command_id) is None


def test_payload_hash_must_be_hex_sha256(world: World) -> None:
    # Red when: any text passes as the request hash.
    for bad in ("g" * 64, "ab" * 31, "AB" * 32):
        with pytest.raises((IntegrityError, DBAPIError)), world.session.begin_nested():
            log_row(world, payload_hash=bad)


def test_undo_revs_must_be_an_object(world: World) -> None:
    # Red when: undo_revs_json may hold a list or a scalar.
    with pytest.raises(IntegrityError), world.session.begin_nested():
        log_row(world, undo_revs=[1])


def test_guard_sets_undo_revs_once_with_the_undo(world: World) -> None:
    # Red when: the guard refuses to set undo_revs_json while undoing a row that has none, lets it
    # change when set, lets it change without the undo, or lets command_id / payload_hash change.
    row = log_row(world)
    undo = "status = 'undone', undone_at = now()"
    refused_sql(world, "UPDATE command_log SET undo_revs_json = '{}' WHERE id = :id", id=row.id)
    refused_sql(
        world,
        f"UPDATE command_log SET {undo}, command_id = gen_random_uuid() WHERE id = :id",
        id=row.id,
    )  # noqa: E501
    refused_sql(
        world,
        f"UPDATE command_log SET {undo}, payload_hash = repeat('c', 64) WHERE id = :id",
        id=row.id,
    )  # noqa: E501
    world.session.execute(
        text(f"UPDATE command_log SET {undo}, undo_revs_json = '{{\"a\": 1}}' WHERE id = :id"),  # noqa: S608
        {"id": row.id},
    )
    kept = log_row(world, undo_revs={"a": 1})
    refused_sql(
        world,
        f"UPDATE command_log SET {undo}, undo_revs_json = '{{\"a\": 2}}' WHERE id = :id",  # noqa: S608
        id=kept.id,
    )
    ok = log_row(world, undo_revs={"a": 1})
    world.session.execute(text(f"UPDATE command_log SET {undo} WHERE id = :id"), {"id": ok.id})  # noqa: S608


def test_command_log_is_never_deleted_by_the_repository(world: World) -> None:
    # Red when: the repository offers a delete.
    row = log_row(world)
    with pytest.raises(NotImplementedError):
        CommandLogRepository(world.session, world.alice.id).delete(row.id)


# --- version trigger --------------------------------------------------------------------------

SECTION_CONTENT = {
    "title", "unit", "weight", "studied_weight", "excluded", "source", "first_page", "last_page",
    "parent_id", "ord",
}  # fmt: skip
SECTION_IGNORED = {"id", "user_id", "subject_id", "document_id", "created_at", "version"}
QUESTION_CONTENT = {
    "level", "prompt", "reference_answer", "rubric", "status", "content_hash", "type_id",
    "answer_text", "answer_origin", "quality_status",
}  # fmt: skip
QUESTION_IGNORED = {
    "id", "user_id", "subject_id", "created_at", "run_id", "source", "kept_at", "unit_rev",
    "bank_document_id", "bank_ord", "generation_id", "version",
}  # fmt: skip


@pytest.mark.parametrize(
    ("table", "content", "ignored"),
    [
        ("doc_section", SECTION_CONTENT, SECTION_IGNORED),
        ("question", QUESTION_CONTENT, QUESTION_IGNORED),
    ],
)
def test_model_columns_classified_for_version_trigger(
    world: World, table: str, content: set[str], ignored: set[str]
) -> None:
    # Red when: a column is added to the model (or the table) without saying whether it is
    # content (the version moves) or not; or the trigger and this list disagree.
    columns = {c.name for c in Base.metadata.tables[table].columns}
    assert columns == content | ignored, columns ^ (content | ignored)
    assert not content & ignored
    in_database = {c["name"] for c in inspect(world.session.connection()).get_columns(table)}
    assert in_database == columns
    source = world.session.execute(
        text("SELECT pg_get_functiondef(p.oid) FROM pg_proc p WHERE proname = :n"),
        {"n": f"{table}_bump_version"},
    ).scalar_one()
    for column in content:
        assert f"NEW.{column} IS DISTINCT FROM OLD.{column}" in source, column
    for column in ignored - {"version"}:
        assert f"NEW.{column} " not in source, column


def version_of(world: World, table: str, id: uuid.UUID) -> int:
    return int(
        world.session.execute(
            text(f"SELECT version FROM {table} WHERE id = :id"),
            {"id": id},  # noqa: S608
        ).scalar_one()
    )


def test_section_version_follows_every_content_write(world: World) -> None:
    # Red when: an edit through the service, or a plain UPDATE, leaves the version alone.
    document = make_document(world.session, world.alice, world.subject)
    section = make_section(world.session, world.alice, document, first_page=1, last_page=5)
    assert version_of(world, "doc_section", section.id) == 1
    service = OutlineService(world.session, world.alice.id)
    service.edit_section(section.id, excluded=True)
    assert version_of(world, "doc_section", section.id) == 2
    service.edit_section(section.id, studied=True)
    assert version_of(world, "doc_section", section.id) == 3
    service.edit_section(section.id, first_page=2, last_page=4)
    assert version_of(world, "doc_section", section.id) == 4
    world.session.execute(
        text("UPDATE doc_section SET title = 'Chương 2' WHERE id = :id"), {"id": section.id}
    )
    assert version_of(world, "doc_section", section.id) == 5
    world.session.refresh(section)
    assert section.version == 5


def test_section_version_ignores_what_the_writer_sends_and_non_content(world: World) -> None:
    # Red when: a client-sent version is kept, a write that changes nothing bumps, or a
    # same-value write of a content column bumps.
    document = make_document(world.session, world.alice, world.subject)
    section = make_section(world.session, world.alice, document)

    def run(sql: str) -> None:
        world.session.execute(text(sql), {"id": section.id})

    run("UPDATE doc_section SET version = 50 WHERE id = :id")
    assert version_of(world, "doc_section", section.id) == 1
    run("UPDATE doc_section SET version = 50, title = 'Mới' WHERE id = :id")
    assert version_of(world, "doc_section", section.id) == 2
    run("UPDATE doc_section SET title = 'Mới' WHERE id = :id")
    assert version_of(world, "doc_section", section.id) == 2
    run("UPDATE doc_section SET created_at = now() WHERE id = :id")
    assert version_of(world, "doc_section", section.id) == 2
    # NULL-safe: first_page NULL -> value is a change; the same NULL again is not.
    run("UPDATE doc_section SET first_page = 1, last_page = 2 WHERE id = :id")
    assert version_of(world, "doc_section", section.id) == 3
    run("UPDATE doc_section SET title = title WHERE id = :id")
    assert version_of(world, "doc_section", section.id) == 3


def test_question_version_follows_retire_answer_type_and_rubric(world: World) -> None:
    # Red when: retire, the answer, the type or the rubric (a JSON value) leave the version alone.
    question = make_question(world.session, world.alice, world.subject)
    questions = QuestionRepository(world.session, world.alice.id)
    assert version_of(world, "question", question.id) == 1

    def run(sql: str) -> None:
        world.session.execute(text(sql), {"id": question.id})

    run("UPDATE question SET answer_text = 'a', answer_origin = 'user' WHERE id = :id")
    assert version_of(world, "question", question.id) == 2
    run("UPDATE question SET rubric = '{\"k\": 1}' WHERE id = :id")
    assert version_of(world, "question", question.id) == 3
    run("UPDATE question SET rubric = '{\"k\": 1}' WHERE id = :id")
    assert version_of(world, "question", question.id) == 3
    assert questions.retire(question.id)
    assert version_of(world, "question", question.id) == 4
    run("UPDATE question SET kept_at = now(), unit_rev = 3, version = 9 WHERE id = :id")
    assert version_of(world, "question", question.id) == 4
    world.session.refresh(question)
    assert question.version == 4


def test_version_check_refuses_zero(world: World) -> None:
    # Red when: version may be below 1.
    document = make_document(world.session, world.alice, world.subject)
    section = make_section(world.session, world.alice, document)
    # The trigger overwrites an UPDATE, so the CHECK is reached only by an insert.
    with pytest.raises(IntegrityError), world.session.begin_nested():
        make_section(world.session, world.alice, document, version=0)
    assert section.version == 1


# --- practice_removal_log ---------------------------------------------------------------------


def test_removal_log_is_append_only(world: World) -> None:
    # Red when: an event can be changed, deleted or truncated.
    question = make_question(world.session, world.alice, world.subject)
    event = PracticeRemovalRepository(world.session, world.alice.id).append(question.id, "removed")
    refused_sql(
        world, "UPDATE practice_removal_log SET action = 'readded' WHERE id = :id", id=event.id
    )  # noqa: E501
    refused_sql(world, "DELETE FROM practice_removal_log WHERE id = :id", id=event.id)
    refused_sql(world, "TRUNCATE practice_removal_log")


def test_removal_log_checks_action_and_owner_of_the_question(world: World) -> None:
    # Red when: any action text passes, or Alice's log can point at Bob's question.
    question = make_question(world.session, world.alice, world.subject)
    bobs = make_question(world.session, world.bob, make_subject(world.session, world.bob))
    repo = PracticeRemovalRepository(world.session, world.alice.id)
    with pytest.raises(IntegrityError), world.session.begin_nested():
        repo.append(question.id, "deleted")
    with pytest.raises(IntegrityError), world.session.begin_nested():
        repo.append(bobs.id, "removed")


def test_removal_log_never_deletes_a_question_with_history(world: World) -> None:
    # Red when: the key to question cascades (a question with a log is dropped with it).
    question = make_question(world.session, world.alice, world.subject)
    PracticeRemovalRepository(world.session, world.alice.id).append(question.id, "removed")
    with pytest.raises(IntegrityError), world.session.begin_nested():
        world.session.execute(text("DELETE FROM question WHERE id = :id"), {"id": question.id})


def test_removal_rev_and_latest_follow_the_newest_event(world: World) -> None:
    # Red when: rev is not 0 with no event, is not the newest id, or in_practice reads an old one.
    question = make_question(world.session, world.alice, world.subject)
    other = make_question(world.session, world.alice, world.subject, n=1)
    repo = PracticeRemovalRepository(world.session, world.alice.id)
    assert (repo.rev(question.id), repo.in_practice(question.id)) == (0, True)
    first = repo.append(question.id, "removed")
    assert (repo.rev(question.id), repo.in_practice(question.id)) == (first.id, False)
    second = repo.append(question.id, "readded", command_id=uuid.uuid4())
    third = repo.append(question.id, "removed")
    assert second.id > first.id
    assert repo.rev(question.id) == third.id
    assert repo.rev(other.id) == 0
    assert repo.latest([question.id])[question.id].id == third.id
    assert set(repo.latest()) == {question.id}


def test_removal_log_is_isolated_between_users(world: World) -> None:
    # Red when: rev / latest / in_practice read another user's events.
    question = make_question(world.session, world.alice, world.subject)
    PracticeRemovalRepository(world.session, world.alice.id).append(question.id, "removed")
    bob = PracticeRemovalRepository(world.session, world.bob.id)
    assert bob.rev(question.id) == 0
    assert bob.latest() == {}
    assert bob.in_practice(question.id) is True


def test_removed_question_stays_removed_after_cache_rebuild(practice: Practice) -> None:
    # Red when: the rebuild takes removed_at from anywhere but the newest log event.
    asked, never = practice.question(), practice.question()
    practice.do(asked, "correct", day(0))
    states = PracticeStateRepository(practice.session, practice.user.id)
    removals = PracticeRemovalRepository(practice.session, practice.user.id)
    removals.append(asked.id, "removed", at=day(1))
    removals.append(never.id, "removed", at=day(1))  # never answered: no state row at all
    assert states.rebuild() == 1
    state = states.state(asked.id)
    assert state is not None
    assert state.removed_at == day(1)
    assert states.row(never.id) is None
    assert removals.in_practice(never.id) is False
    removals.append(asked.id, "readded", at=day(2))
    states.rebuild()
    state = states.state(asked.id)
    assert state is not None
    assert state.removed_at is None
    removals.append(asked.id, "removed", at=day(3))
    states.rebuild([asked.id])
    state = states.state(asked.id)
    assert state is not None
    assert state.removed_at == day(3)


def test_rebuild_keeps_removed_at_of_a_question_without_log_events(practice: Practice) -> None:
    # Red when: rows removed before 0032 (no event yet) come back after a rebuild.
    question = practice.question()
    practice.do(question, "correct", day(0))
    states = PracticeStateRepository(practice.session, practice.user.id)
    assert states.set_removed_at(question.id, day(1))
    states.rebuild()
    row = practice.session.query(PracticeStateRow).filter_by(question_id=question.id).one()
    assert row.removed_at == day(1)


# --- study_filter -----------------------------------------------------------------------------


def test_study_filter_set_clear_keeps_the_row_and_raises_rev(world: World) -> None:
    # Red when: clear deletes the row (rev returns to 1: ABA) or rev stays when only mode changes.
    repo = StudyFilterRepository(world.session, world.alice.id)
    assert repo.get(world.subject.id).rev == 0
    assert repo.lock(world.subject.id).rev == 0
    assert repo.set(world.subject.id, "only", date(2026, 11, 9)).rev == 1
    assert repo.set(world.subject.id, "defer", date(2026, 11, 10)).rev == 2
    cleared = repo.clear(world.subject.id)
    assert (cleared.mode, cleared.until, cleared.rev) == (None, None, 3)
    assert repo.lock(world.subject.id).rev == 3
    assert repo.set(world.subject.id, "only", date(2026, 11, 9)).rev == 4
    rows = world.session.execute(
        text("SELECT count(*) FROM study_filter WHERE user_id = :u"), {"u": world.alice.id}
    ).scalar_one()
    assert rows == 1


def test_study_filter_is_isolated_and_refuses_unknown_mode_or_foreign_subject(
    world: World,
) -> None:
    # Red when: Bob reads Alice's filter, a filter sits on another user's subject, or any mode
    # text passes.
    alice = StudyFilterRepository(world.session, world.alice.id)
    alice.set(world.subject.id, "only", date(2026, 11, 9))
    bob = StudyFilterRepository(world.session, world.bob.id)
    assert bob.get(world.subject.id).rev == 0
    with pytest.raises(IntegrityError), world.session.begin_nested():
        bob.set(world.subject.id, "only", date(2026, 11, 9))
    with pytest.raises(IntegrityError), world.session.begin_nested():
        alice.set(world.other_subject.id, "skip", date(2026, 11, 9))


def test_study_filter_follows_its_subject_and_user(world: World) -> None:
    # Red when: a filter outlives its subject.
    StudyFilterRepository(world.session, world.alice.id).set(
        world.other_subject.id, "defer", date(2026, 11, 9)
    )
    world.session.execute(
        text("DELETE FROM subject WHERE id = :id"), {"id": world.other_subject.id}
    )
    assert (
        world.session.execute(
            text("SELECT count(*) FROM study_filter WHERE subject_id = :id"),
            {"id": world.other_subject.id},
        ).scalar_one()
        == 0
    )


# --- up and down ------------------------------------------------------------------------------


def test_0032_up_down_up_keeps_old_command_rows_and_the_old_guard(
    engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: old command_log rows lose data or get no command_id; the downgrade leaves the new
    # columns, tables or triggers; or it does not bring back the 0025 guard. Committed on
    # purpose (Alembic runs on its own connection).
    user = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text('INSERT INTO "user" (id, email) VALUES (:u, :e)'),
            {"u": user, "e": f"{user}@example.com"},
        )
    try:
        command.downgrade(alembic_cfg, "0031")
        with engine.connect() as c:
            tables = set(inspect(c).get_table_names())
            columns = {col["name"] for col in inspect(c).get_columns("command_log")}
        assert "practice_removal_log" not in tables
        assert "study_filter" not in tables
        assert not columns & {"command_id", "payload_hash", "undo_revs_json"}
        with engine.begin() as c:
            old = c.execute(
                text(
                    "INSERT INTO command_log (id, user_id, raw_text, ops_json, inverse_json,"
                    " affected_count) VALUES (gen_random_uuid(), :u, 'gộp', '[]', '[]', 0)"
                    " RETURNING id"
                ),
                {"u": user},
            ).scalar_one()
        command.upgrade(alembic_cfg, "head")
        with engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT command_id, payload_hash, undo_revs_json, raw_text FROM command_log"
                    " WHERE id = :id"
                ),
                {"id": old},
            ).one()
        assert row.command_id is not None
        assert row.payload_hash == "0" * 64
        assert row.undo_revs_json is None
        assert row.raw_text == "gộp"
        with engine.connect() as c:
            default = c.execute(
                text(
                    "SELECT column_default FROM information_schema.columns"
                    " WHERE table_name = 'command_log'"
                    " AND column_name IN ('command_id', 'payload_hash')"
                    " AND column_default IS NOT NULL"
                )
            ).all()
        assert default == []  # the fill-in defaults are gone
    finally:
        try:
            command.upgrade(alembic_cfg, "head")
        finally:
            with engine.begin() as c:
                c.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": user})
