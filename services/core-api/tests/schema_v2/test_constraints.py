"""T7.1: the v2 schema group 1 refuses what the spec forbids (ADR-0008, spec v2 §16.2).

Each case is one wrong row; the database, not the code, says no."""

import uuid
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from core_api.db.models import (
    DocSection,
    Document,
    Question,
    QuestionSection,
    Submission,
    UnitRevision,
    UnitSection,
)
from v2_rows import (
    NOW,
    World,
    make_document,
    make_question,
    make_section,
    make_study_session,
    make_type,
    make_unit,
)


def add(world: World, row: Any) -> None:
    world.session.add(row)
    world.session.flush()


def doc(world: World, **kw: Any) -> Document:
    return make_document(world.session, world.alice, world.subject, **kw)


def second_doc(world: World, **kw: Any) -> Document:
    return make_document(world.session, world.alice, world.subject, "cd" * 32, **kw)


def section_row(world: World, document: Document, **kw: Any) -> DocSection:
    values: dict[str, Any] = {
        "user_id": world.alice.id,
        "subject_id": document.subject_id,
        "document_id": document.id,
        "ord": 0,
        "title": "Chương 1",
        "unit": "page",
        "source": "bookmark",
    }
    values.update(kw)
    return DocSection(**values)


# --- document ---------------------------------------------------------------------------------


@pytest.mark.parametrize("column,value", [("role", "main"), ("format", "txt")])
def test_document_columns_reject_unknown_values(world: World, column: str, value: str) -> None:
    # Red when: the document.role / document.format CHECK is missing.
    with pytest.raises(IntegrityError):
        doc(world, **{column: value})


def test_one_textbook_per_subject(world: World) -> None:
    # Red when: the partial unique index lets a second textbook into the same subject.
    doc(world, role="textbook")
    with pytest.raises(IntegrityError):
        second_doc(world, role="textbook")


@pytest.mark.parametrize("status", ["rejected", "failed"])
def test_dead_textbook_does_not_block_a_new_one(world: World, status: str) -> None:
    # Red when: a refused or failed file keeps the textbook place of its subject (review F7).
    extra: dict[str, Any] = (
        {"failure_reason": "unreadable", "uploaded_at": NOW} if status == "failed" else {}
    )
    dead = doc(world, role="textbook", status=status, **extra)
    assert dead.role == "textbook"
    second_doc(world, role="textbook")


def test_other_subject_may_have_a_textbook(world: World) -> None:
    doc(world, role="textbook")
    make_document(world.session, world.alice, world.other_subject, role="textbook")


def test_many_auxiliary_and_bank_documents_allowed(world: World) -> None:
    doc(world, role="auxiliary")
    second_doc(world, role="question_bank")
    make_document(world.session, world.alice, world.subject, "ef" * 32, role="auxiliary")


def test_document_defaults_are_auxiliary_pdf(world: World) -> None:
    document = doc(world)
    world.session.refresh(document)
    assert (document.role, document.format) == ("auxiliary", "pdf")


# --- doc_section ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"unit": "chapter"},
        {"source": "guess"},
        {"ord": -1},
        {"weight": -0.5},
        {"title": "  "},
    ],
    ids=["unit", "source", "ord", "weight", "title"],
)
def test_doc_section_rejects_bad_values(world: World, overrides: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError):
        add(world, section_row(world, doc(world), **overrides))


def test_doc_section_defaults(world: World) -> None:
    section = make_section(world.session, world.alice, doc(world))
    world.session.refresh(section)
    assert (section.weight, section.excluded, section.parent_id) == (1, False, None)


def test_section_is_not_its_own_parent(world: World) -> None:
    section = make_section(world.session, world.alice, doc(world))
    section.parent_id = section.id
    with pytest.raises(IntegrityError):
        world.session.flush()


def test_section_parent_in_same_document_ok(world: World) -> None:
    document = doc(world)
    parent = make_section(world.session, world.alice, document)
    make_section(world.session, world.alice, document, parent_id=parent.id, ord=1)


def test_section_parent_other_document_refused(world: World) -> None:
    # Red when: parent_id is only tied to (id, user_id): the tree would cross documents.
    parent = make_section(world.session, world.alice, doc(world))
    with pytest.raises(IntegrityError):
        make_section(world.session, world.alice, second_doc(world), parent_id=parent.id)


def test_section_on_another_users_document_refused(world: World) -> None:
    document = doc(world)
    with pytest.raises(IntegrityError):
        add(world, section_row(world, document, user_id=world.bob.id))


def test_section_subject_must_match_document(world: World) -> None:
    document = doc(world)
    with pytest.raises(IntegrityError):
        add(world, section_row(world, document, subject_id=world.other_subject.id))


def test_section_order_may_repeat_while_reordering(world: World) -> None:
    document = doc(world)
    make_section(world.session, world.alice, document, ord=0)
    make_section(world.session, world.alice, document, ord=0)


# --- knowledge_unit ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["draft", "canonical", "retired", "merged"])
def test_unit_status_accepts_the_four_values(world: World, status: str) -> None:
    make_unit(world.session, world.alice, world.subject, status=status)


def test_unit_status_rejects_unknown(world: World) -> None:
    with pytest.raises(IntegrityError):
        make_unit(world.session, world.alice, world.subject, status="deleted")


def test_new_unit_defaults_canonical_version1(world: World) -> None:
    # Red when: the default is not canonical (0031).
    unit = make_unit(world.session, world.alice, world.subject)
    world.session.refresh(unit)
    assert (unit.status, unit.version) == ("canonical", 1)


def test_unit_version_from_one(world: World) -> None:
    with pytest.raises(IntegrityError):
        make_unit(world.session, world.alice, world.subject, version=0)


# --- unit_revision ----------------------------------------------------------------------------


def revision(world: World, unit_id: uuid.UUID, **kw: Any) -> UnitRevision:
    values: dict[str, Any] = {
        "user_id": world.alice.id,
        "unit_id": unit_id,
        "rev": 0,
        "origin": "ai",
        "content": {"title": "t"},
    }
    values.update(kw)
    return UnitRevision(**values)


@pytest.mark.parametrize(
    "bad", [{"origin": "bot"}, {"rev": -1}, {"content": [1]}], ids=["origin", "rev", "content"]
)
def test_unit_revision_rejects_bad_values(world: World, bad: dict[str, Any]) -> None:
    unit = make_unit(world.session, world.alice, world.subject)
    with pytest.raises(IntegrityError):
        add(world, revision(world, unit.id, **bad))


def test_unit_revision_unique_per_unit_and_rev(world: World) -> None:
    unit = make_unit(world.session, world.alice, world.subject)
    add(world, revision(world, unit.id))
    add(world, revision(world, unit.id, rev=1, origin="user"))
    with pytest.raises(IntegrityError):
        add(world, revision(world, unit.id))


def test_unit_revision_on_another_users_unit_refused(world: World) -> None:
    unit = make_unit(world.session, world.alice, world.subject)
    with pytest.raises(IntegrityError):
        add(world, revision(world, unit.id, user_id=world.bob.id))


# --- unit_section / question_section ----------------------------------------------------------


def unit_section(world: World, unit_id: uuid.UUID, section_id: uuid.UUID) -> UnitSection:
    return UnitSection(
        user_id=world.alice.id, subject_id=world.subject.id, unit_id=unit_id, section_id=section_id
    )


def test_unit_section_links_same_subject(world: World) -> None:
    unit = make_unit(world.session, world.alice, world.subject)
    section = make_section(world.session, world.alice, doc(world))
    add(world, unit_section(world, unit.id, section.id))


def test_section_link_other_subject_refused(world: World) -> None:
    # Red when: the composite foreign keys lack subject_id.
    unit = make_unit(world.session, world.alice, world.other_subject)
    section = make_section(world.session, world.alice, doc(world))
    with pytest.raises(IntegrityError):
        add(world, unit_section(world, unit.id, section.id))


def test_unit_section_unique_pair(world: World) -> None:
    unit = make_unit(world.session, world.alice, world.subject)
    section = make_section(world.session, world.alice, doc(world))
    add(world, unit_section(world, unit.id, section.id))
    with pytest.raises(IntegrityError):
        add(world, unit_section(world, unit.id, section.id))


def test_question_section_links_and_refuses_other_subject(world: World) -> None:
    section = make_section(world.session, world.alice, doc(world))
    good = make_question(world.session, world.alice, world.subject, 1)
    bad = make_question(world.session, world.alice, world.other_subject, 2)
    base = {"user_id": world.alice.id, "subject_id": world.subject.id, "section_id": section.id}
    add(world, QuestionSection(question_id=good.id, **base))
    with pytest.raises(IntegrityError):
        add(world, QuestionSection(question_id=bad.id, **base))


# --- question_type ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [{"name": " "}, {"ref_time_s": 0}, {"ref_origin": "guess"}],
    ids=["name", "ref_time", "ref_origin"],
)
def test_question_type_rejects_bad_values(world: World, overrides: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError):
        make_type(world.session, world.alice, world.subject, **overrides)


def test_question_type_name_unique_per_subject(world: World) -> None:
    make_type(world.session, world.alice, world.subject)
    make_type(world.session, world.alice, world.other_subject)
    with pytest.raises(IntegrityError):
        make_type(world.session, world.alice, world.subject)


def test_type_other_subject_refused(world: World) -> None:
    kind = make_type(world.session, world.alice, world.other_subject)
    with pytest.raises(IntegrityError):
        make_question(world.session, world.alice, world.subject, type_id=kind.id)


def test_delete_type_keeps_questions(world: World) -> None:
    # Red when: type_id cascades, so dropping a type drops its questions (review F2).
    kind = make_type(world.session, world.alice, world.subject)
    make_question(world.session, world.alice, world.subject, type_id=kind.id)
    world.session.delete(kind)
    with pytest.raises(IntegrityError):
        world.session.flush()


# --- question ---------------------------------------------------------------------------------


def test_question_defaults(world: World) -> None:
    question = make_question(world.session, world.alice, world.subject)
    world.session.refresh(question)
    assert question.source == "review_auto"
    assert question.quality_status == "ok"
    assert question.type_id is None and question.kept_at is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "web"},
        {"quality_status": "meh"},
        {"answer_origin": "bot", "answer_text": "a"},
        {"unit_rev": -1},
        {"answer_text": "a"},
        {"answer_origin": "ai"},
        {"source": "review_auto", "run_id": None},
    ],
    ids=[
        "source",
        "quality",
        "answer_origin",
        "unit_rev",
        "text_without_origin",
        "origin_without_text",
        "review_auto_needs_run",
    ],
)
def test_question_rejects_bad_values(world: World, overrides: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError):
        make_question(world.session, world.alice, world.subject, **overrides)


def test_bank_question_without_run_id_or_units(world: World) -> None:
    question = make_question(
        world.session,
        world.alice,
        world.subject,
        source="bank",
        run_id=None,
        answer_text="Đáp án của đề",
        answer_origin="bank",
    )
    assert question.run_id is None
    assert world.session.scalars(select(Question).where(Question.id == question.id)).one()


# --- submission -------------------------------------------------------------------------------


def submission(world: World, **kw: Any) -> Submission:
    study = make_study_session(world.session, world.alice, world.subject)
    values: dict[str, Any] = {
        "user_id": world.alice.id,
        "session_id": study.id,
        "status": "queued",
    }
    values.update(kw)
    return Submission(**values)


def test_submission_defaults(world: World) -> None:
    row = submission(world)
    add(world, row)
    world.session.refresh(row)
    assert row.file_keys == [] and row.started_at is None and row.finished_at is None


def test_submission_rejects_unknown_status(world: World) -> None:
    with pytest.raises(IntegrityError):
        add(world, submission(world, status="lost"))


@pytest.mark.parametrize(
    "overrides",
    [{"status": "done"}, {"status": "failed"}, {"status": "queued", "finished_at": NOW}],
    ids=["done_needs_finish", "failed_needs_finish", "queued_has_no_finish"],
)
def test_submission_finish_stamp_matches_status(world: World, overrides: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError):
        add(world, submission(world, **overrides))


def test_submission_done_with_finish_ok(world: World) -> None:
    add(world, submission(world, status="done", finished_at=NOW))
    add(world, submission(world, status="pending_ai"))


def test_submission_on_another_users_session_refused(world: World) -> None:
    with pytest.raises(IntegrityError):
        add(world, submission(world, user_id=world.bob.id))


# --- names ------------------------------------------------------------------------------------


def test_constraint_and_index_names_within_63(world: World) -> None:
    # Red when: a generated name is cut by Postgres, so a later migration cannot drop it.
    too_long = world.session.execute(
        text(
            "SELECT conname FROM pg_constraint WHERE length(conname) > 63"
            " UNION SELECT indexname FROM pg_indexes WHERE length(indexname) > 63"
        )
    ).all()
    assert too_long == []
