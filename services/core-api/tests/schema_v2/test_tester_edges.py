"""T7.1, tester edges (spec v2 §16.2, plan "Bảng": every foreign key to a user's table is
ON DELETE CASCADE except question.type_id; no AC): what goes with a document, and what stays."""

from sqlalchemy import text

from core_api.db.models import QuestionSection, UnitSection
from v2_rows import World, make_document, make_question, make_section, make_unit


def count(world: World, sql: str, **params: object) -> int:
    return world.session.execute(text(sql), params).scalar_one()


def test_deleting_a_document_takes_its_outline_and_links_not_units_or_questions(
    world: World,
) -> None:
    # Red when: doc_section -> document, doc_section.parent_id, unit_section.section_id or
    # question_section.section_id lose ON DELETE CASCADE (the delete is then refused, e.g. in
    # document_cleanup), or a link cascades the wrong way and takes the unit or question with it.
    s, a, sub = world.session, world.alice, world.subject
    document = make_document(s, a, sub)
    parent = make_section(s, a, document)
    child = make_section(s, a, document, parent_id=parent.id, ord=1)
    unit = make_unit(s, a, sub)
    question = make_question(s, a, sub)
    s.add(UnitSection(user_id=a.id, subject_id=sub.id, unit_id=unit.id, section_id=child.id))
    s.add(
        QuestionSection(
            user_id=a.id, subject_id=sub.id, question_id=question.id, section_id=child.id
        )
    )
    s.flush()

    s.execute(text("DELETE FROM document WHERE id = :id"), {"id": document.id})

    assert (
        count(world, "SELECT count(*) FROM doc_section WHERE document_id = :d", d=document.id) == 0
    )
    assert count(world, "SELECT count(*) FROM unit_section WHERE unit_id = :u", u=unit.id) == 0
    assert (
        count(world, "SELECT count(*) FROM question_section WHERE question_id = :q", q=question.id)
        == 0
    )
    assert count(world, "SELECT count(*) FROM knowledge_unit WHERE id = :u", u=unit.id) == 1
    assert count(world, "SELECT count(*) FROM question WHERE id = :q", q=question.id) == 1


def test_deleting_a_parent_section_takes_its_subtree(world: World) -> None:
    # Red when: doc_section.parent_id loses ON DELETE CASCADE (removing a chapter is refused
    # while it has sub-sections) or turns SET NULL (the children float up to the top).
    s, a = world.session, world.alice
    document = make_document(s, a, world.subject)
    parent = make_section(s, a, document)
    child = make_section(s, a, document, parent_id=parent.id, ord=1)
    make_section(s, a, document, parent_id=child.id, ord=2)
    sibling = make_section(s, a, document, ord=3)

    s.execute(text("DELETE FROM doc_section WHERE id = :id"), {"id": parent.id})

    left = world.session.execute(
        text("SELECT id FROM doc_section WHERE document_id = :d"), {"d": document.id}
    ).scalars()
    assert set(left) == {sibling.id}
