"""T4.17 tester: edge cases of `session.processed.v1` the coder's tests left open (mutation run
29/10). Storage is a double; the database is real."""

import uuid

import pytest
from pydantic import ValidationError
from result_builders import anchor, encode, question, result, unit
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_session_processed_handler import World, count
from test_session_processed_handler import storage as storage  # noqa: F401
from test_session_processed_handler import world as world  # noqa: F401

from core_api.db.models import Anchor, KnowledgeUnit, Question, QuestionUnit, UnitLineage, User
from core_api.domain.session_result import clean, parse_result
from core_api.handlers.session_processed import OnSessionProcessed
from fake_storage import FakeStorage

U1, U2 = uuid.uuid4(), uuid.uuid4()
RUN = uuid.uuid4()


def _unit_of(user: User, subject_id: uuid.UUID, title: str = "Cũ") -> KnowledgeUnit:
    return KnowledgeUnit(
        user_id=user.id, subject_id=subject_id, title=title, summary="s", kind="concept", run_id=RUN
    )


def test_event_naming_another_users_session_with_its_key_is_refused(
    db_session: Session,
    two_users: tuple[User, User],
    storage: FakeStorage,  # noqa: F811
) -> None:
    # Red when: neither the session nor its subject is looked up under the event's user. The key
    # is Alice's own derived key, so the consumer's prefix check is bypassed here on purpose: the
    # handler's owner checks must stand on their own.
    alice, bob = two_users
    a = World(db_session, alice, storage)
    key = a.put(a.body(units=[a.unit(U1)], questions=[question([U1], prompt="Lén")]))
    OnSessionProcessed(storage)(db_session, a.event(key, user=bob))
    assert (count(db_session, KnowledgeUnit), count(db_session, Question)) == (0, 0)


def test_result_of_a_draft_session_writes_nothing(world: World) -> None:  # noqa: F811
    # Red when: the status check is dropped. The coder's draft test passes even then: its file
    # names the confirmed session, so `clean` refuses it for the wrong reason. Here the file is
    # the draft's own, so only the status check stops it.
    draft = world.confirmed("draft")
    body = result(draft.id, units=[world.unit(U1)], questions=[question([U1], prompt="Nháp")])
    key = world.put(body, world.key(draft))
    OnSessionProcessed(world.storage)(world.db, world.event(key, study=draft))
    assert (count(world.db, KnowledgeUnit), count(world.db, Question)) == (0, 0)


def test_blank_quote_drops_the_anchor_not_the_event(world: World) -> None:  # noqa: F811
    # Red when: a whitespace-only quote is kept: the quote_not_blank CHECK fails and the whole
    # session result is lost.
    world.run(
        world.body(
            units=[
                world.unit(U1, anchors=[anchor(world.document.id, quote_text="  \n")]),
                world.unit(
                    U2,
                    anchors=[
                        anchor(world.document.id, quote_text="\t"),
                        anchor(world.document.id),
                    ],
                ),
            ]
        )
    )
    assert count(world.db, KnowledgeUnit) == 1
    assert count(world.db, Anchor) == 1


def test_same_prompt_twice_in_one_file_adds_one_question_and_its_own_links(
    world: World,  # noqa: F811
) -> None:
    # Red when: the second copy is linked to the first question (find_by_prompt skip dropped), or
    # a second active question is stored.
    world.run(
        world.body(
            units=[world.unit(U1), world.unit(U2)],
            questions=[question([U1], prompt="Cùng câu"), question([U2], prompt="Cùng  câu ")],
        )
    )
    assert count(world.db, Question) == 1
    assert count(world.db, QuestionUnit) == 1


def test_merge_with_a_quote_the_unit_has_adds_no_second_anchor(world: World) -> None:  # noqa: F811
    # Red when: a merge re-adds a quote its unit already holds (redelivered or repeated merge).
    old = _unit_of(world.user, world.subject.id)
    world.db.add(old)
    world.db.flush()
    merge = {"existing_unit_id": str(old.id), "anchors": [anchor(world.document.id)]}
    world.run(world.body(merges=[merge, merge]))
    world.run(world.body(merges=[merge]))
    assert count(world.db, Anchor) == 1


def test_lineage_listed_twice_writes_one_row(world: World) -> None:  # noqa: F811
    # Red when: lineage ids are not de-duplicated: UNIQUE(old, new) fails and the whole session
    # result is lost (the event raises).
    old = _unit_of(world.user, world.subject.id)
    world.db.add(old)
    world.db.flush()
    world.run(world.body(units=[world.unit(U1, lineage=[str(old.id), str(old.id)])]))
    assert count(world.db, UnitLineage) == 1
    assert count(world.db, KnowledgeUnit) == 2


def test_lineage_to_another_users_unit_writes_nothing_for_it(
    db_session: Session,
    two_users: tuple[User, User],
    storage: FakeStorage,  # noqa: F811
) -> None:
    # Red when: a result of Alice records lineage from Bob's unit (or the event fails on it).
    alice, bob = two_users
    a, b = World(db_session, alice, storage), World(db_session, bob, storage)
    theirs = _unit_of(bob, b.subject.id)
    db_session.add(theirs)
    db_session.flush()
    a.run(a.body(units=[a.unit(U1, lineage=[str(theirs.id)])]))
    assert count(db_session, UnitLineage) == 0
    assert count(db_session, KnowledgeUnit, alice) == 1


def test_level3_naming_one_unit_twice_is_dropped(world: World) -> None:  # noqa: F811
    # Red when: unit ids are counted before de-duplication: a level-3 question joins one unit.
    world.run(
        world.body(
            units=[world.unit(U1)],
            questions=[question([U1, U1], 3, prompt="L3 giả"), question([U1, U1], 1, prompt="L1")],
        )
    )
    assert [(q.prompt, q.level) for q in world.db.scalars(select(Question))] == [("L1", 1)]
    assert count(world.db, QuestionUnit) == 1


@pytest.mark.parametrize("part", ["unit", "anchor", "merge", "question", "dropped", "skipped"])
def test_extra_field_inside_an_item_breaks_the_contract(part: str) -> None:
    # Red when: a nested model is not closed (the contract has additionalProperties: false at
    # every level).
    session, doc = uuid.uuid4(), uuid.uuid4()
    body = result(
        session,
        units=[unit(U1, doc)],
        merges=[{"existing_unit_id": str(U2), "anchors": [anchor(doc)]}],
        questions=[question([U1])],
        skipped=[{"kind": "page", "ref": 1, "reason": "no_text"}],
    )
    target = {
        "unit": body["units"][0],
        "anchor": body["units"][0]["anchors"][0],
        "merge": body["merges"][0],
        "question": body["questions"][0],
        "dropped": body["dropped"],
        "skipped": body["skipped"][0],
    }[part]
    target["sneaky"] = "x"
    with pytest.raises(ValidationError):
        parse_result(encode(body))


@pytest.mark.parametrize("field", ["title", "prompt", "reference_answer", "rubric"])
def test_whitespace_only_text_drops_the_item(field: str) -> None:
    # Red when: a text is checked before strip: whitespace-only text reaches the not_blank CHECK and
    # the whole event fails (or a blank question is stored).
    session, doc = uuid.uuid4(), uuid.uuid4()
    units = [unit(U1, doc), unit(U2, doc)]
    questions = [question([U2], prompt="Giữ")]
    blank = " \t 　"
    if field == "title":
        units[0]["title"] = blank
    else:
        questions.append(question([U1]) | {field: blank})
    out = clean(
        parse_result(encode(result(session, units=units, questions=questions))),
        study_session_id=session,
        documents={doc},
    )
    if field == "title":
        assert [u.unit_id for u in out.units] == [U2]
    assert [q.prompt for q in out.questions] == ["Giữ"]


def test_whitespace_only_title_does_not_fail_the_event(world: World) -> None:  # noqa: F811
    # Red when: the not_blank CHECK on knowledge_unit.title is reached (IntegrityError).
    world.run(world.body(units=[world.unit(U1, title="  "), world.unit(U2)]))
    assert count(world.db, KnowledgeUnit) == 1


def test_title_cut_to_200_after_nul_removed_fits_the_column(world: World) -> None:  # noqa: F811
    # Red when: the title is cut before NUL removal or not cut at all (DataError on String(200)).
    world.run(world.body(units=[world.unit(U1, title="\x00" * 50 + "ạ" * 250)]))
    row = world.db.scalars(select(KnowledgeUnit)).one()
    assert row.title == "ạ" * 200
