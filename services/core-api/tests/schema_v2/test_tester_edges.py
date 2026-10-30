"""T7.1, tester edges (spec v2 §16.2, plan "Bảng": every foreign key to a user's table is
ON DELETE CASCADE except question.type_id; no AC): what goes with a document, and what stays,
the boundaries of the new checks, two users, and the models agreeing with migration 0023."""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from core_api.db.base import Base
from core_api.db.models import QuestionSection, Submission, UnitRevision, UnitSection
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


# --- what goes with a unit, a question, a study session ---------------------------------------


def test_deleting_a_unit_takes_its_revisions_and_section_links(world: World) -> None:
    # Red when: unit_revision.unit_id or unit_section.unit_id loses ON DELETE CASCADE (merging
    # or dropping a draft unit is then refused), or the link takes the section with it.
    s, a, sub = world.session, world.alice, world.subject
    section = make_section(s, a, make_document(s, a, sub))
    unit = make_unit(s, a, sub)
    s.add(UnitRevision(user_id=a.id, unit_id=unit.id, rev=0, origin="ai", content={}))
    s.add(UnitSection(user_id=a.id, subject_id=sub.id, unit_id=unit.id, section_id=section.id))
    s.flush()

    s.execute(text("DELETE FROM knowledge_unit WHERE id = :id"), {"id": unit.id})

    assert count(world, "SELECT count(*) FROM unit_revision WHERE unit_id = :u", u=unit.id) == 0
    assert count(world, "SELECT count(*) FROM unit_section WHERE unit_id = :u", u=unit.id) == 0
    assert count(world, "SELECT count(*) FROM doc_section WHERE id = :x", x=section.id) == 1


def test_deleting_a_question_takes_its_section_links(world: World) -> None:
    # Red when: question_section.question_id loses ON DELETE CASCADE (a rejected generated
    # question cannot be dropped), or the link takes the section with it.
    s, a, sub = world.session, world.alice, world.subject
    section = make_section(s, a, make_document(s, a, sub))
    question = make_question(s, a, sub)
    s.add(
        QuestionSection(
            user_id=a.id, subject_id=sub.id, question_id=question.id, section_id=section.id
        )
    )
    s.flush()

    s.execute(text("DELETE FROM question WHERE id = :id"), {"id": question.id})

    assert (
        count(world, "SELECT count(*) FROM question_section WHERE section_id = :x", x=section.id)
        == 0
    )
    assert count(world, "SELECT count(*) FROM doc_section WHERE id = :x", x=section.id) == 1


def test_deleting_a_study_session_takes_its_submissions(world: World) -> None:
    # Red when: submission.session_id loses ON DELETE CASCADE: a study session with work handed
    # in can no longer be deleted.
    s, a = world.session, world.alice
    study = make_study_session(s, a, world.subject)
    s.add(Submission(user_id=a.id, session_id=study.id, status="queued"))
    s.flush()

    s.execute(text("DELETE FROM study_session WHERE id = :id"), {"id": study.id})

    assert count(world, "SELECT count(*) FROM submission WHERE session_id = :x", x=study.id) == 0


# --- links never cross subjects or users ------------------------------------------------------


@pytest.mark.parametrize("link", ["unit_section", "question_section"])
def test_link_to_a_section_of_another_subject_refused(world: World, link: str) -> None:
    # Red when: the section side of unit_section / question_section is tied by (id, user_id)
    # only: a unit or question of one subject then counts on the outline of another.
    s, a, sub = world.session, world.alice, world.subject
    other_section = make_section(s, a, make_document(s, a, world.other_subject))
    if link == "unit_section":
        unit = make_unit(s, a, sub)
        row: Any = UnitSection(
            user_id=a.id, subject_id=sub.id, unit_id=unit.id, section_id=other_section.id
        )
    else:
        question = make_question(s, a, sub)
        row = QuestionSection(
            user_id=a.id, subject_id=sub.id, question_id=question.id, section_id=other_section.id
        )
    s.add(row)
    with pytest.raises(IntegrityError):
        s.flush()


def test_question_section_pair_is_unique(world: World) -> None:
    # Red when: uq(question_id, section_id) is missing: the same question counts twice towards
    # a section's readiness.
    s, a, sub = world.session, world.alice, world.subject
    section = make_section(s, a, make_document(s, a, sub))
    question = make_question(s, a, sub)
    for _ in range(2):
        s.add(
            QuestionSection(
                user_id=a.id, subject_id=sub.id, question_id=question.id, section_id=section.id
            )
        )
    with pytest.raises(IntegrityError):
        s.flush()


# --- boundaries of the checks -----------------------------------------------------------------


def test_lowest_allowed_values_are_accepted(world: World) -> None:
    # Red when: a check is tightened past the spec: weight 0 (an empty section), ord 0, rev 0
    # (the AI's), unit_rev 0, version 1, ref_time_s 1 must all be stored.
    s, a, sub = world.session, world.alice, world.subject
    section = make_section(s, a, make_document(s, a, sub), weight=0, ord=0)
    unit = make_unit(s, a, sub, version=1)
    s.add(UnitRevision(user_id=a.id, unit_id=unit.id, rev=0, origin="ai", content={}))
    make_type(s, a, sub, ref_time_s=1)
    make_question(s, a, sub, unit_rev=0)
    s.flush()
    assert section.weight == 0


@pytest.mark.parametrize("blank", [" 　", "\t\n", "   "])
@pytest.mark.parametrize("table", ["doc_section", "question_type"])
def test_unicode_blank_titles_refused(world: World, table: str, blank: str) -> None:
    # Red when: the not-blank check only knows the ASCII space: a PDF heading made of no-break
    # or ideographic spaces becomes an empty section title (or an empty question type name).
    s, a = world.session, world.alice
    with pytest.raises(IntegrityError):
        if table == "doc_section":
            make_section(s, a, make_document(s, a, world.subject), title=blank)
        else:
            make_type(s, a, world.subject, name=blank)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_section_weight_must_be_finite(world: World, bad: float) -> None:
    # Red when: weight is checked only with `weight >= 0`: Postgres orders NaN above every
    # number, so NaN passes and poisons every progress sum over the outline (spec v2 §16.2,
    # weight in `unit`s, >= 0).
    s, a = world.session, world.alice
    with pytest.raises(IntegrityError):
        make_section(s, a, make_document(s, a, world.subject), weight=bad)


# --- one textbook per subject, and only the textbook is one per subject -----------------------


def test_several_question_banks_in_one_subject_allowed(world: World) -> None:
    # Red when: the partial index keys on more than role = 'textbook' (e.g. role <> 'auxiliary'):
    # a subject with two question bank files (two past exams) is then refused.
    s, a, sub = world.session, world.alice, world.subject
    make_document(s, a, sub, role="textbook")
    make_document(s, a, sub, "cd" * 32, role="question_bank")
    make_document(s, a, sub, "ef" * 32, role="question_bank")


@pytest.mark.parametrize("status", ["pending", "uploaded"])
def test_live_textbook_blocks_a_second_one(world: World, status: str) -> None:
    # Red when: the partial index skips a live status: two textbooks in one subject.
    # (`indexed` is left out: it needs the derived keys; like these, it is not in the NOT IN.)
    s, a, sub = world.session, world.alice, world.subject
    extra: dict[str, Any] = {} if status == "pending" else {"uploaded_at": NOW}
    make_document(s, a, sub, role="textbook", status=status, **extra)
    with pytest.raises(IntegrityError, match="uq_document_textbook_per_subject"):
        make_document(s, a, sub, "cd" * 32, role="textbook")


def test_promoting_or_reviving_a_second_textbook_refused(world: World) -> None:
    # Red when: the index is checked on INSERT only in the code's mind: setting role to textbook
    # on an auxiliary file, or bringing a failed textbook back, must hit it too.
    s, a, sub = world.session, world.alice, world.subject
    make_document(s, a, sub, role="textbook")
    auxiliary = make_document(s, a, sub, "cd" * 32)
    dead = make_document(
        s,
        a,
        sub,
        "ef" * 32,
        role="textbook",
        status="failed",
        failure_reason="unreadable",
        uploaded_at=NOW,
    )
    for row, column, value in ((auxiliary, "role", "textbook"), (dead, "status", "uploaded")):
        with (
            pytest.raises(IntegrityError, match="uq_document_textbook_per_subject"),
            s.begin_nested(),
        ):
            s.execute(
                text(f"UPDATE document SET {column} = :v, failure_reason = NULL WHERE id = :id"),
                {"v": value, "id": row.id},
            )


# --- submission through its life --------------------------------------------------------------


def test_submission_moves_through_its_statuses(world: World) -> None:
    # Red when: the status check or finished_iff_ended refuses a step of the normal path
    # (queued -> processing -> pending_ai -> processing -> done) or lets `done` drop its stamp.
    s, a = world.session, world.alice
    row = Submission(
        user_id=a.id, session_id=make_study_session(s, a, world.subject).id, status="queued"
    )
    s.add(row)
    s.flush()
    for status in ("processing", "pending_ai", "processing"):
        row.status, row.started_at = status, NOW
        s.flush()
    row.status, row.finished_at = "done", NOW
    s.flush()
    with pytest.raises(IntegrityError, match="finished_iff_ended"), s.begin_nested():
        s.execute(text("UPDATE submission SET finished_at = NULL WHERE id = :id"), {"id": row.id})


# --- the models say what migration 0023 built -------------------------------------------------

TOUCHED = (
    "document",
    "doc_section",
    "knowledge_unit",
    "unit_revision",
    "unit_section",
    "question",
    "question_type",
    "question_section",
    "submission",
)
MIRROR = "t71_model_mirror"


def facts(connection: Connection, schema: str) -> dict[str, set[tuple[str, ...]]]:
    """Constraints, indexes and column defaults of the touched tables, schema name removed."""

    def clean(sql: str | None) -> str:
        return (sql or "").replace(f"{schema}.", "").replace(f'"{schema}".', "")

    params = {"s": schema, "t": list(TOUCHED)}
    constraints = connection.execute(
        text(
            "SELECT c.relname, con.conname, pg_get_constraintdef(con.oid) FROM pg_constraint con"
            " JOIN pg_class c ON c.oid = con.conrelid"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = :s AND c.relname = ANY(:t)"
        ),
        params,
    ).all()
    indexes = connection.execute(
        text(
            "SELECT tablename, indexname, indexdef FROM pg_indexes"
            " WHERE schemaname = :s AND tablename = ANY(:t)"
        ),
        params,
    ).all()
    columns = connection.execute(
        text(
            "SELECT table_name, column_name, coalesce(column_default, ''), is_nullable, data_type"
            " FROM information_schema.columns WHERE table_schema = :s AND table_name = ANY(:t)"
        ),
        params,
    ).all()
    return {
        "constraints": {(t, n, clean(d)) for t, n, d in constraints},
        "indexes": {(t, n, clean(d)) for t, n, d in indexes},
        "columns": {(t, c, clean(d), nl, ty) for t, c, d, nl, ty in columns},
    }


@pytest.fixture
def mirror(world: World) -> Iterator[Connection]:
    """The models built with create_all in a schema of their own, inside the test's transaction
    (rolled back with it)."""
    connection = world.session.connection()
    connection.execute(text(f"CREATE SCHEMA {MIRROR}"))
    Base.metadata.create_all(connection.execution_options(schema_translate_map={None: MIRROR}))
    yield connection


@pytest.mark.parametrize("kind", ["constraints", "indexes", "columns"])
def test_models_match_migration_0023(mirror: Connection, kind: str) -> None:
    # Red when: a model and migration 0023 disagree on something `alembic check` does not
    # compare: a CHECK's text (a status or role list), a partial index's WHERE (the textbook
    # rule, the retry queue), a server default, or an ON DELETE. Later migrations are written
    # from the models, so the drift would land in the database unseen.
    built, migrated = facts(mirror, MIRROR)[kind], facts(mirror, "public")[kind]
    assert built - migrated == set() and migrated - built == set()
