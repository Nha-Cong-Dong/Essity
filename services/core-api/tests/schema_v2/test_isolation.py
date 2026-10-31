"""T7.1 (ADR-0008 user isolation, T1.3 helper; spec v2 §16.2; no AC): the new tables of user
data are isolated by user and go with their user."""

from typing import Any

import pytest
from sqlalchemy import text

from core_api.db.base import UserOwned
from core_api.db.models import (
    DocSection,
    QuestionSection,
    QuestionType,
    Submission,
    UnitRevision,
    UnitSection,
)
from core_api.repositories.base import UserScopedRepository
from isolation import assert_isolated
from v2_rows import (
    World,
    make_document,
    make_question,
    make_section,
    make_study_session,
    make_type,
    make_unit,
)

MODELS = [DocSection, UnitRevision, UnitSection, QuestionType, QuestionSection, Submission]


def repository_of(model: type[Any]) -> type[UserScopedRepository[Any]]:
    return type(f"{model.__name__}Repository", (UserScopedRepository,), {"model": model})


def build(world: World, model: type[Any]) -> UserOwned:
    """A row of `model` for Alice's subject (the repository stamps the owner)."""
    s, a, sub = world.session, world.alice, world.subject
    if model is QuestionType:
        return QuestionType(subject_id=sub.id, name="n", ref_time_s=60, ref_origin="user")
    document = make_document(s, a, sub)
    section = make_section(s, a, document)
    if model is DocSection:
        return DocSection(
            subject_id=sub.id,
            document_id=document.id,
            ord=1,
            page_start=1,
            page_end=1,
            title="t",
            unit="page",
            source="user",
        )
    unit = make_unit(s, a, sub)
    if model is UnitRevision:
        return UnitRevision(unit_id=unit.id, rev=0, origin="ai", content={})
    if model is UnitSection:
        return UnitSection(subject_id=sub.id, unit_id=unit.id, section_id=section.id)
    if model is QuestionSection:
        question = make_question(s, a, sub)
        return QuestionSection(subject_id=sub.id, question_id=question.id, section_id=section.id)
    assert model is Submission
    return Submission(session_id=make_study_session(s, a, sub).id, status="queued")


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_new_tables_are_isolated(world: World, model: type[Any]) -> None:
    assert_isolated(
        world.session,
        repository_of(model),
        world.alice,
        world.bob,
        lambda repository: repository.add(build(world, model)),
    )


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_deleting_the_user_removes_the_rows(world: World, model: type[Any]) -> None:
    # Red when: a foreign key to the user or to a parent lacks ON DELETE CASCADE.
    repository_of(model)(world.session, world.alice.id).add(build(world, model))
    world.session.flush()
    world.session.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": world.alice.id})
    count = world.session.execute(
        text(f"SELECT count(*) FROM {model.__tablename__} WHERE user_id = :id"),
        {"id": world.alice.id},
    ).scalar_one()
    assert count == 0


@pytest.mark.parametrize("parent", ["user", "subject"])
def test_deleting_user_or_subject_cascades_through_typed_questions(
    world: World, parent: str
) -> None:
    # Red when: question.type_id is switched to RESTRICT: the type and its questions then block
    # the delete of their own subject or user.
    kind = make_type(world.session, world.alice, world.subject)
    make_question(world.session, world.alice, world.subject, type_id=kind.id)
    table, key = (
        ("subject", world.subject.id) if parent == "subject" else ('"user"', world.alice.id)
    )
    world.session.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": key})
    for name in ("question", "question_type"):
        left = world.session.execute(
            text(f"SELECT count(*) FROM {name} WHERE subject_id = :s"), {"s": world.subject.id}
        ).scalar_one()
        assert left == 0
