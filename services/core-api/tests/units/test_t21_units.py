"""T2.1: knowledge units, anchors, questions (layer 2, ADR-0008), plan
`docs/plans/t2.1-t2.3-units-review-history.md` (D3, D4, D9, D12; review plan P2, P3).

The data side of us-02b AC1/AC3/AC5 and us-04b AC1; their behaviour comes with T2.2, T4.15, T5.1.
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clock import future_exam
from core_api.db.models import Anchor, KnowledgeUnit, Question, Subject, User
from core_api.db.models.unit import ANCHOR_SOURCES, UNIT_KINDS
from core_api.domain.question_hash import content_hash
from core_api.repositories.question import (
    QuestionConflictError,
    QuestionRepository,
    QuestionUnitRepository,
    SubjectMismatchError,
)
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.unit import AnchorRepository, KnowledgeUnitRepository, UnitNotFoundError
from isolation import assert_isolated

RUN = uuid.uuid4()


def subject(session: Session, user: User, name: str = "Mạng máy tính") -> Subject:
    made, _ = SubjectRepository(session, user.id).create_with_exam(name, future_exam())
    return made


def unit(session: Session, user: User, of: Subject, title: str = "Giao thức TCP") -> KnowledgeUnit:
    return KnowledgeUnitRepository(session, user.id).create(
        of.id, title=title, summary="Truyền tin cậy", kind="concept", run_id=RUN
    )


def question(session: Session, user: User, of: Subject, prompt: str = "TCP là gì?") -> Question:
    return QuestionRepository(session, user.id).add_idempotent(
        of.id, level=1, prompt=prompt, reference_answer="Giao thức tin cậy", run_id=RUN
    )


def anchor(session: Session, user: User, of: KnowledgeUnit, **fields: Any) -> Anchor:
    values: dict[str, Any] = {
        "source": "document",
        "quote_text": "TCP đảm bảo thứ tự",
        "run_id": RUN,
    }
    return AnchorRepository(session, user.id).create(of.id, **(values | fields))


# --- Fine-grained anchors (T2.1 "Xong khi", ADR-0008) ------------------------------------------


def test_t21_anchor_has_all_fine_grained_fields(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    owner = unit(db_session, alice, subject(db_session, alice))
    made = anchor(
        db_session,
        alice,
        owner,
        page_no=12,
        char_start=40,
        char_end=90,
        bbox=[[1.0, 2.0, 3.0, 4.0]],
    )
    db_session.flush()
    db_session.refresh(made)
    assert (made.page_no, made.char_start, made.char_end) == (12, 40, 90)
    assert made.bbox == [[1.0, 2.0, 3.0, 4.0]]


@pytest.mark.parametrize(
    "fields",
    [
        {"char_start": 10, "char_end": 5},  # end before start
        {"char_start": 10},  # only one end of the range
        {"char_start": -1, "char_end": 3},
        {"page_no": 0},
        {"bbox": {"x": 1}},  # not an array
    ],
)
def test_t21_anchor_range_checks(
    db_session: Session, two_users: tuple[User, User], fields: dict[str, Any]
) -> None:
    alice, _ = two_users
    owner = unit(db_session, alice, subject(db_session, alice))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        anchor(db_session, alice, owner, **fields)
        db_session.flush()


def test_us02b_ac3_anchor_requires_quote_text(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    owner = unit(db_session, alice, subject(db_session, alice))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        anchor(db_session, alice, owner, quote_text="   ")
        db_session.flush()


@pytest.mark.parametrize("source", sorted(ANCHOR_SOURCES))
def test_us02b_ac5_unit_with_only_one_kind_of_anchor(
    db_session: Session, two_users: tuple[User, User], source: str
) -> None:
    # A unit made only from notes, or only from a document, is a unit all the same.
    alice, _ = two_users
    owner = unit(db_session, alice, subject(db_session, alice))
    anchor(db_session, alice, owner, source=source)
    db_session.flush()


def test_t21_anchor_source_outside_the_list_is_refused(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    owner = unit(db_session, alice, subject(db_session, alice))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        anchor(db_session, alice, owner, source="website")
        db_session.flush()


# --- Units (us-02b AC1, data side) -------------------------------------------------------------


def test_us02b_ac1_kind_accepts_the_five_and_refuses_others(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    assert UNIT_KINDS == {"concept", "mechanism", "comparison", "formula", "example"}  # PRD US-02b
    of = subject(db_session, alice)
    units = KnowledgeUnitRepository(db_session, alice.id)
    for kind in sorted(UNIT_KINDS):
        units.create(of.id, title=kind, summary="s", kind=kind, run_id=RUN)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        units.create(of.id, title="x", summary="s", kind="anecdote", run_id=RUN)
        db_session.flush()


def test_us02b_ac1_unit_has_title_and_summary(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    of = subject(db_session, alice)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        KnowledgeUnitRepository(db_session, alice.id).create(
            of.id, title="  ", summary="s", kind="concept", run_id=RUN
        )
        db_session.flush()


def test_t21_unit_needs_a_subject_of_the_same_user(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    with pytest.raises(SubjectNotFoundError):
        unit(db_session, bob, subject(db_session, alice))


# --- Questions (us-04b AC1, D3, D12) -----------------------------------------------------------


def test_us04b_ac1_question_level_is_1_to_3(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    of = subject(db_session, alice)
    questions = QuestionRepository(db_session, alice.id)
    for level in (1, 2, 3):
        questions.add_idempotent(
            of.id, level=level, prompt=f"Câu {level}", reference_answer="a", run_id=RUN
        )
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        questions.add_idempotent(of.id, level=4, prompt="Câu 4", reference_answer="a", run_id=RUN)
        db_session.flush()


def test_us04b_ac1_question_links_one_or_more_units(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    of = subject(db_session, alice)
    asked = question(db_session, alice, of)
    links = QuestionUnitRepository(db_session, alice.id)
    links.link(asked.id, unit(db_session, alice, of, "TCP").id)
    links.link(asked.id, unit(db_session, alice, of, "UDP").id)
    db_session.flush()
    assert len(links.units_of(asked.id)) == 2


def test_t21_content_hash_unique_per_user_and_subject(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    of = subject(db_session, alice)
    db_session.flush()
    raw = {"user": alice.id, "subject": of.id, "hash": content_hash("TCP là gì?"), "run": RUN}
    insert = text(
        "INSERT INTO question (id, user_id, subject_id, level, prompt, reference_answer, status,"
        " content_hash, run_id) VALUES (gen_random_uuid(), :user, :subject, 1, 'TCP là gì?', 'a',"
        " 'active', :hash, :run)"
    )
    db_session.execute(insert, raw)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(insert, raw)


def test_t21_add_idempotent_same_subject_returns_existing(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Running a seed twice on the same subject must not double its questions (T2.2).
    alice, _ = two_users
    of = subject(db_session, alice)
    first = question(db_session, alice, of, "TCP là gì?")
    again = question(db_session, alice, of, "  TCP   là gì? ")  # the same once normalised
    db_session.flush()
    assert again.id == first.id
    assert len(QuestionRepository(db_session, alice.id).list()) == 1


def test_t21_same_question_in_two_subjects_gives_two_rows(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: the second subject's question is dropped in silence (PM start gate, D12).
    alice, _ = two_users
    networks = subject(db_session, alice, "Mạng máy tính")
    systems = subject(db_session, alice, "Hệ điều hành")
    first = question(db_session, alice, networks, "Định nghĩa giao thức?")
    second = question(db_session, alice, systems, "Định nghĩa giao thức?")
    db_session.flush()
    assert first.id != second.id


def test_t21_two_users_may_have_the_same_question(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    question(db_session, alice, subject(db_session, alice))
    question(db_session, bob, subject(db_session, bob))
    db_session.flush()


def test_t21_question_and_unit_of_different_subjects_cannot_be_linked(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    asked = question(db_session, alice, subject(db_session, alice, "Mạng máy tính"))
    other = unit(db_session, alice, subject(db_session, alice, "Hệ điều hành"))
    with pytest.raises(SubjectMismatchError):
        QuestionUnitRepository(db_session, alice.id).link(asked.id, other.id)


# --- run_id (T2.1 "Xong khi") ------------------------------------------------------------------


@pytest.mark.parametrize("table", ["knowledge_unit", "anchor", "question"])
def test_t21_run_id_has_no_foreign_key(db_session: Session, table: str) -> None:
    # run_id points into the ai database (ADR-0008): no foreign key can reach it.
    foreign = inspect(db_session.connection()).get_foreign_keys(table)
    assert not [fk for fk in foreign if "run_id" in fk["constrained_columns"]]


# --- Isolation (ADR-0001) ----------------------------------------------------------------------


def test_t21_isolation_unit(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    of = subject(db_session, alice)
    assert_isolated(
        db_session,
        KnowledgeUnitRepository,
        alice,
        bob,
        lambda units: units.create(of.id, title="t", summary="s", kind="concept", run_id=RUN),
    )


def test_t21_isolation_anchor(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    owner = unit(db_session, alice, subject(db_session, alice))
    assert_isolated(
        db_session,
        AnchorRepository,
        alice,
        bob,
        lambda anchors: anchors.create(owner.id, source="document", quote_text="q", run_id=RUN),
    )


def test_t21_isolation_question(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    of = subject(db_session, alice)
    assert_isolated(
        db_session,
        QuestionRepository,
        alice,
        bob,
        lambda questions: questions.add_idempotent(
            of.id, level=1, prompt="p", reference_answer="a", run_id=RUN
        ),
    )


def test_t21_isolation_question_unit(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    of = subject(db_session, alice)
    asked, owner = question(db_session, alice, of), unit(db_session, alice, of)
    assert_isolated(
        db_session,
        QuestionUnitRepository,
        alice,
        bob,
        lambda links: links.link(asked.id, owner.id),
    )


def test_t21_anchor_on_someone_elses_unit_is_refused(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    owner = unit(db_session, alice, subject(db_session, alice))
    with pytest.raises(UnitNotFoundError):
        anchor(db_session, bob, owner)


# --- The database itself refuses a link across users, whatever the code does (P2) -------------


def _seed_two_users(session: Session, alice: User, bob: User) -> dict[str, uuid.UUID]:
    a_subject, b_subject = subject(session, alice), subject(session, bob)
    unit(session, alice, a_subject)
    b_unit = unit(session, bob, b_subject)
    a_question = question(session, alice, a_subject)
    session.flush()
    return {
        "alice": alice.id,
        "b_subject": b_subject.id,
        "b_unit": b_unit.id,
        "a_question": a_question.id,
        "a_subject": a_subject.id,
        "run": RUN,
    }


CROSS_USER_INSERTS = {
    "unit -> subject": "INSERT INTO knowledge_unit (id, user_id, subject_id, title, summary, kind,"
    " status, run_id) VALUES (gen_random_uuid(), :alice, :b_subject, 't', 's', 'concept',"
    " 'active', :run)",
    "anchor -> unit": "INSERT INTO anchor (id, user_id, unit_id, source, quote_text, run_id)"
    " VALUES (gen_random_uuid(), :alice, :b_unit, 'document', 'q', :run)",
    "question -> subject": "INSERT INTO question (id, user_id, subject_id, level, prompt,"
    " reference_answer, status, content_hash, run_id) VALUES (gen_random_uuid(), :alice,"
    " :b_subject, 1, 'p', 'a', 'active', repeat('a', 64), :run)",
    "question_unit -> unit": "INSERT INTO question_unit (id, user_id, subject_id, question_id,"
    " unit_id) VALUES (gen_random_uuid(), :alice, :a_subject, :a_question, :b_unit)",
}


@pytest.mark.parametrize("edge", sorted(CROSS_USER_INSERTS))
def test_t21_cross_user_link_refused_raw_sql(
    db_session: Session, two_users: tuple[User, User], edge: str
) -> None:
    # Red when: a foreign key is on the id alone, so raw SQL (or a repository bug) can attach
    # Alice's row to Bob's.
    alice, bob = two_users
    ids = _seed_two_users(db_session, alice, bob)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(text(CROSS_USER_INSERTS[edge]), ids)


def test_t21_question_unit_subjects_must_match_in_the_database(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    asked = question(db_session, alice, subject(db_session, alice, "Mạng máy tính"))
    other_subject = subject(db_session, alice, "Hệ điều hành")
    other = unit(db_session, alice, other_subject)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(
            text(
                "INSERT INTO question_unit (id, user_id, subject_id, question_id, unit_id) VALUES"
                " (gen_random_uuid(), :user, :subject, :question, :unit)"
            ),
            {"user": alice.id, "subject": other_subject.id, "question": asked.id, "unit": other.id},
        )


# --- content_hash (D3) -------------------------------------------------------------------------


def test_t21_content_hash_normalises_and_keeps_case() -> None:
    assert content_hash("TCP là gì?") == content_hash("  TCP\tlà   gì? ")
    assert content_hash("Mạng") == content_hash("Mạng")  # NFC
    assert content_hash("N là gì?") != content_hash("n là gì?")  # no casefold
    assert len(content_hash("x")) == 64


# --- A seed run again with a changed answer is refused, not silently ignored (review 8a92b17) -----


@pytest.mark.parametrize(
    "change",
    [{"reference_answer": "Đáp án đã sửa"}, {"level": 2}, {"rubric": {"must": ["thứ tự"]}}],
)
def test_t21_same_prompt_with_other_fields_changed_is_a_conflict(
    db_session: Session, two_users: tuple[User, User], change: dict[str, Any]
) -> None:
    # Red when: add_idempotent hands back the old row, and a corrected reference answer in the
    # seed never reaches the database (T2.12 would grade against the wrong one).
    alice, _ = two_users
    of = subject(db_session, alice)
    question(db_session, alice, of, "TCP là gì?")
    fields: dict[str, Any] = {"level": 1, "reference_answer": "Giao thức tin cậy", "rubric": None}
    with pytest.raises(QuestionConflictError):
        QuestionRepository(db_session, alice.id).add_idempotent(
            of.id, prompt="TCP là gì?", run_id=RUN, **(fields | change)
        )


@pytest.mark.parametrize("column", ["prompt", "reference_answer"])
def test_t21_question_text_cannot_be_blank(
    db_session: Session, two_users: tuple[User, User], column: str
) -> None:
    alice, _ = two_users
    of = subject(db_session, alice)
    values = {"prompt": "TCP là gì?", "reference_answer": "a"} | {column: "   "}
    with pytest.raises(IntegrityError), db_session.begin_nested():
        QuestionRepository(db_session, alice.id).add_idempotent(
            of.id, level=1, run_id=RUN, **values
        )
