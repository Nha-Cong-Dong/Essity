"""T7.M2, migration 0025 (ADR-0008, additions only; ARCH §6.2; no user story, so no AC): the
group 2 tables refuse what the plan forbids. Each case is one wrong row; the database, not the
code, says no."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from core_api.db.models import (
    CommandLog,
    KnowledgeUnit,
    PracticeLog,
    PracticeState,
    Question,
    UnitEdge,
)
from v2_rows import (
    NOW,
    World,
    make_document,
    make_grade,
    make_question,
    make_subject,
    make_type,
    make_unit,
)

NEW_TABLES = ("practice_state", "practice_log", "command_log", "unit_edge")


def add(world: World, row: Any) -> Any:
    world.session.add(row)
    world.session.flush()
    return row


def refused(world: World, row: Any) -> None:
    with pytest.raises(IntegrityError), world.session.begin_nested():
        add(world, row)


def refused_sql(world: World, sql: str, **params: Any) -> None:
    """Refused by a trigger itself, not by a key or a CHECK that happens to fire."""
    with pytest.raises(DBAPIError, match="is refused"), world.session.begin_nested():
        world.session.execute(text(sql), params)


# --- practice_state ---------------------------------------------------------------------------


def state(world: World, question: Question, **kw: Any) -> PracticeState:
    values: dict[str, Any] = {
        "user_id": world.alice.id,
        "question_id": question.id,
        "phase": "review",
        "stability": 3.0,
        "difficulty": 5.0,
        "due": NOW + timedelta(days=3),
        "last_review": NOW,
    }
    values.update(kw)
    return PracticeState(**values)


def test_practice_state_unique_per_question(world: World) -> None:
    # Red when: UNIQUE (user_id, question_id) is missing, so a question has two schedules.
    question = make_question(world.session, world.alice, world.subject)
    add(world, state(world, question))
    refused(world, state(world, question))


def test_practice_state_removed_at_keeps_row(world: World) -> None:
    # Red when: removing a question from practice has to delete its schedule.
    question = make_question(world.session, world.alice, world.subject)
    row = add(world, state(world, question, removed_at=NOW))
    assert row.removed_at == NOW


def test_practice_state_other_users_question_refused(world: World) -> None:
    # Red when: the key to question is on id alone.
    bobs = make_question(world.session, world.bob, make_subject(world.session, world.bob))
    refused(world, state(world, bobs))


@pytest.mark.parametrize(
    "values",
    [{"phase": "relearning"}, {"phase": "review", "step": 0}, {"phase": "learning"}],
    ids=["relearning_without_step", "review_with_step", "unknown_phase"],
)
def test_practice_state_phase_and_step_rule(world: World, values: dict[str, Any]) -> None:
    # Red when: step and phase may disagree, or a phase outside review/relearning is stored.
    question = make_question(world.session, world.alice, world.subject)
    refused(world, state(world, question, **values))
    add(world, state(world, question, phase="relearning", step=0))


# --- practice_log -----------------------------------------------------------------------------


def log(world: World, question: Question, grade_id: uuid.UUID | None, **kw: Any) -> PracticeLog:
    values: dict[str, Any] = {
        "user_id": world.alice.id,
        "question_id": question.id,
        "rating": 3,
        "reviewed_at": NOW,
        "grade_id": grade_id,
    }
    values.update(kw)
    return PracticeLog(**values)


def graded(world: World, n: int = 0) -> tuple[Question, uuid.UUID]:
    question = make_question(world.session, world.alice, world.subject, n)
    return question, make_grade(world.session, world.alice, world.subject, question).id


@pytest.mark.parametrize("rating", [0, 5])
def test_practice_rating_outside_one_to_four_refused(world: World, rating: int) -> None:
    # Red when: the rating CHECK is missing or too wide.
    question, grade_id = graded(world)
    refused(world, log(world, question, grade_id, rating=rating))


@pytest.mark.parametrize("rating", [1, 2, 3, 4])
def test_practice_rating_one_to_four_accepted(world: World, rating: int) -> None:
    # Red when: the CHECK stops at 3 (practice has Easy, ADR-0029).
    question, grade_id = graded(world, rating)
    add(world, log(world, question, grade_id, rating=rating))


def test_practice_log_one_row_per_grade(world: World) -> None:
    # Red when: UNIQUE (grade_id) is missing, so one answer is logged twice.
    question, grade_id = graded(world)
    add(world, log(world, question, grade_id))
    refused(world, log(world, question, grade_id))


def test_practice_log_needs_a_grade(world: World) -> None:
    # Red when: grade_id is nullable (an append-only row could never be linked later).
    question, _ = graded(world)
    refused(world, log(world, question, None))


def test_practice_log_refuses_update_delete_truncate(world: World) -> None:
    # Red when: the append-only triggers are missing on practice_log.
    question, grade_id = graded(world)
    row = add(world, log(world, question, grade_id))
    refused_sql(world, "UPDATE practice_log SET rating = 1 WHERE id = :id", id=row.id)
    refused_sql(world, "DELETE FROM practice_log WHERE id = :id", id=row.id)
    refused_sql(world, "TRUNCATE practice_log")


def test_user_delete_blocked_by_practice_log_like_review_log(world: World) -> None:
    # Red when: deleting the account silently erases practice history (T2.22 opens the way).
    question, grade_id = graded(world)
    add(world, log(world, question, grade_id))
    refused_sql(world, 'DELETE FROM "user" WHERE id = :id', id=world.alice.id)


def test_practice_log_other_users_grade_refused(world: World) -> None:
    # Red when: the key to grade is on id alone.
    bob_subject = make_subject(world.session, world.bob)
    bobs = make_question(world.session, world.bob, bob_subject)
    bobs_grade = make_grade(world.session, world.bob, bob_subject, bobs)
    mine, _ = graded(world)
    refused(world, log(world, mine, bobs_grade.id))


def test_practice_tables_never_touch_review_tables(world: World) -> None:
    # Red when: a practice write also writes the unit schedule (two independent schedules).
    question, grade_id = graded(world)
    add(world, state(world, question))
    add(world, log(world, question, grade_id))
    for table in ("review_log", "memory_state"):
        count = world.session.execute(
            text(f"SELECT count(*) FROM {table} WHERE user_id = :u"),  # noqa: S608
            {"u": world.alice.id},
        ).scalar_one()
        assert count == 0


# --- command_log ------------------------------------------------------------------------------


def command(world: World, **kw: Any) -> CommandLog:
    values: dict[str, Any] = {
        "user_id": world.alice.id,
        "subject_id": world.subject.id,
        "raw_text": "gộp hai thẻ",
        "ops_json": [{"op": "merge"}],
        "inverse_json": [{"op": "split"}],
        "status": "applied",
        "affected_count": 2,
    }
    values.update(kw)
    return CommandLog(**values)


def test_command_log_accepts_a_global_command(world: World) -> None:
    add(world, command(world, subject_id=None, screen_session_id=uuid.uuid4()))


def test_command_log_other_users_subject_refused(world: World) -> None:
    # Red when: the key to subject is on id alone.
    refused(world, command(world, subject_id=make_subject(world.session, world.bob).id))


@pytest.mark.parametrize(
    "values",
    [
        {"raw_text": "  "},
        {"ops_json": {"op": "merge"}},
        {"inverse_json": "x"},
        {"status": "gone"},
        {"affected_count": -1},
        {"status": "undone"},
        {"undone_at": NOW},
    ],
    ids=["blank", "ops_not_array", "inverse_not_array", "bad_status", "negative", "no_time", "no_undo"],
)
def test_command_log_checks(world: World, values: dict[str, Any]) -> None:
    refused(world, command(world, **values))


def test_command_log_update_only_undo_once(world: World) -> None:
    # Red when: the guard lets a log be rewritten or undone twice.
    row = add(world, command(world))
    for sql in (
        "UPDATE command_log SET inverse_json = '[]' WHERE id = :id",
        "UPDATE command_log SET raw_text = 'x' WHERE id = :id",
        "UPDATE command_log SET status = 'undone' WHERE id = :id",
        "UPDATE command_log SET status = 'undone', undone_at = now(), affected_count = 9"
        " WHERE id = :id",
    ):
        refused_sql(world, sql, id=row.id)
    world.session.execute(
        text("UPDATE command_log SET status = 'undone', undone_at = now() WHERE id = :id"),
        {"id": row.id},
    )
    refused_sql(world, "UPDATE command_log SET undone_at = now() WHERE id = :id", id=row.id)
    refused_sql(world, "UPDATE command_log SET status = 'applied' WHERE id = :id", id=row.id)


def test_command_log_follows_subject_delete(world: World) -> None:
    # Not review history: deleting the subject takes the log with it.
    add(world, command(world))
    world.session.execute(text("DELETE FROM subject WHERE id = :id"), {"id": world.subject.id})
    left = world.session.execute(
        text("SELECT count(*) FROM command_log WHERE user_id = :u"), {"u": world.alice.id}
    ).scalar_one()
    assert left == 0


# --- unit_edge --------------------------------------------------------------------------------

LOW = uuid.UUID(int=1 << 120)
HIGH = uuid.UUID(int=2 << 120)
QUOTE = {"unit_id": "x", "quote": "TCP là giao thức tin cậy"}


def two_units(world: World) -> tuple[KnowledgeUnit, KnowledgeUnit]:
    return (
        make_unit(world.session, world.alice, world.subject, id=LOW),
        make_unit(world.session, world.alice, world.subject, id=HIGH),
    )


def edge(world: World, src: KnowledgeUnit, dst: KnowledgeUnit, **kw: Any) -> UnitEdge:
    values: dict[str, Any] = {
        "user_id": world.alice.id,
        "subject_id": src.subject_id,
        "src_unit_id": src.id,
        "dst_unit_id": dst.id,
        "kind": "prerequisite",
        "origin": "ai",
        "status": "proposed",
        "evidence": [QUOTE],
    }
    values.update(kw)
    return UnitEdge(**values)


def test_unit_edge_other_users_unit_refused(world: World) -> None:
    # Red when: either unit key is on id alone.
    src, dst = two_units(world)
    bobs = make_unit(world.session, world.bob, make_subject(world.session, world.bob))
    refused(world, edge(world, src, bobs))
    refused(world, edge(world, bobs, dst, subject_id=src.subject_id))


def test_unit_edge_cross_subject_refused(world: World) -> None:
    # Red when: an edge may join units of two subjects.
    src, _ = two_units(world)
    other = make_unit(world.session, world.alice, world.other_subject)
    refused(world, edge(world, src, other))
    refused(world, edge(world, src, other, subject_id=world.other_subject.id))


def test_unit_edge_ai_needs_evidence(world: World) -> None:
    src, dst = two_units(world)
    refused(world, edge(world, src, dst, evidence=[]))


def test_unit_edge_user_may_omit_evidence(world: World) -> None:
    src, dst = two_units(world)
    add(world, edge(world, src, dst, origin="user", evidence=[], status="active"))


@pytest.mark.parametrize("evidence", [{"quote": "x"}, "x", 3])
def test_unit_edge_evidence_must_be_array(world: World, evidence: Any) -> None:
    src, dst = two_units(world)
    refused(world, edge(world, src, dst, origin="user", evidence=evidence))


def test_unit_edge_stores_two_quotes_from_both_cards(world: World) -> None:
    # Red when: the evidence holds one quote only, or ties it to one card.
    src, dst = two_units(world)
    quotes = [{"unit_id": str(src.id), "quote": "a"}, {"unit_id": str(dst.id), "quote": "b"}]
    row = add(world, edge(world, src, dst, evidence=quotes))
    world.session.refresh(row)
    assert row.evidence == quotes


def test_unit_edge_unique_kind(world: World) -> None:
    src, dst = two_units(world)
    add(world, edge(world, src, dst))
    refused(world, edge(world, src, dst))
    add(world, edge(world, src, dst, kind="part_of"))


def test_unit_edge_contrast_src_lt_dst_both_directions(world: World) -> None:
    # Red when: a contrast may go either way, so one pair is stored twice.
    low, high = two_units(world)
    add(world, edge(world, low, high, kind="contrast"))
    refused(world, edge(world, high, low, kind="contrast"))
    add(world, edge(world, high, low, kind="prerequisite"))


def test_unit_edge_not_to_itself(world: World) -> None:
    low, _ = two_units(world)
    refused(world, edge(world, low, low))


@pytest.mark.parametrize(
    "values", [{"kind": "likes"}, {"origin": "bot"}, {"status": "maybe"}], ids=["k", "o", "s"]
)
def test_unit_edge_enums(world: World, values: dict[str, Any]) -> None:
    src, dst = two_units(world)
    refused(world, edge(world, src, dst, **values))


def test_unit_edge_goes_with_its_unit(world: World) -> None:
    src, dst = two_units(world)
    add(world, edge(world, src, dst))
    world.session.execute(text("DELETE FROM knowledge_unit WHERE id = :id"), {"id": dst.id})
    left = world.session.execute(
        text("SELECT count(*) FROM unit_edge WHERE user_id = :u"), {"u": world.alice.id}
    ).scalar_one()
    assert left == 0


# --- question bank columns, question_type.ref_origin ------------------------------------------


def test_question_bank_link_needs_document_same_subject_user(world: World) -> None:
    # Red when: the bank key is missing or leaves out subject or user.
    mine = make_document(world.session, world.alice, world.subject, role="question_bank")
    other_subject = make_document(
        world.session, world.alice, world.other_subject, "cd" * 32, role="question_bank"
    )
    bobs = make_document(world.session, world.bob, make_subject(world.session, world.bob), "ef" * 32)
    ok = make_question(world.session, world.alice, world.subject, 1, bank_document_id=mine.id)
    assert ok.bank_document_id == mine.id
    for n, document in enumerate((other_subject, bobs), start=2):
        with pytest.raises(IntegrityError), world.session.begin_nested():
            make_question(
                world.session, world.alice, world.subject, n, bank_document_id=document.id
            )


def test_question_bank_ord_needs_document_and_not_negative(world: World) -> None:
    document = make_document(world.session, world.alice, world.subject, role="question_bank")
    for n, values in enumerate(
        ({"bank_ord": 1}, {"bank_document_id": document.id, "bank_ord": -1}), start=1
    ):
        with pytest.raises(IntegrityError), world.session.begin_nested():
            make_question(world.session, world.alice, world.subject, n, **values)
    make_question(
        world.session, world.alice, world.subject, 3, bank_document_id=document.id, bank_ord=0
    )


def test_bank_document_delete_blocked_when_questions_linked(world: World) -> None:
    # Red when: deleting the question bank takes questions that already have a schedule.
    document = make_document(world.session, world.alice, world.subject, role="question_bank")
    make_question(world.session, world.alice, world.subject, 1, bank_document_id=document.id)
    with pytest.raises(IntegrityError), world.session.begin_nested():
        world.session.execute(text("DELETE FROM document WHERE id = :id"), {"id": document.id})


def test_question_type_default_origin_accepted(world: World) -> None:
    # Red when: the CHECK of 0023 still refuses 'default'.
    make_type(world.session, world.alice, world.subject, ref_origin="default")


# --- Every new foreign key carries user_id ----------------------------------------------------


def test_new_fks_all_include_user_id(world: World) -> None:
    # Red when: a foreign key of a new table or of the bank link is on ids alone.
    rows = world.session.execute(
        text(
            "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)"
            " FROM pg_constraint WHERE contype = 'f' AND conrelid::regclass::text = ANY(:t)"
            " AND confrelid::regclass::text <> 'user'"
            " AND (conrelid::regclass::text <> 'question' OR conname LIKE '%bank%')"
        ),
        {"t": [*NEW_TABLES, "question"]},
    ).all()
    assert len(rows) >= 7
    assert [name for _, name, definition in rows if "user_id" not in definition] == []
