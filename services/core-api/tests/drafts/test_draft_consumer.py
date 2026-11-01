"""T7.8 (US-02b AC1, AC6, AC10, AC13, Bảo mật): the consumer of `submission.processed.v1` and
`submission.failed.v1` writes draft cards once, trusts neither the event nor the file."""

import uuid

import pytest
from draft_world import World
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.db.models import (
    Anchor,
    KnowledgeUnit,
    Question,
    UnitRevision,
    UnitSection,
    User,
)
from core_api.handlers.session_result_v2 import OnSubmissionProcessed, on_submission_failed
from fake_storage import FakeStorage


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def world(db_session: Session, two_users: tuple[User, User], storage: FakeStorage) -> World:
    return World(db_session, two_users[0], storage)


def run(
    world: World, key: str | None = None, drafts: list[dict[str, object]] | None = None
) -> None:
    key = key or world.put(drafts if drafts is not None else [world.draft(1), world.draft(2)])
    OnSubmissionProcessed(world.storage)(world.db, world.processed(key))


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_ac13_resent_event_makes_no_duplicate_drafts(world: World) -> None:
    # Red when: the (session, draft_key) unique index or ON CONFLICT is missing.
    key = world.put([world.draft(1), world.draft(2)])
    run(world, key)
    world.submission.status = "processing"  # the same file arrives again, in a new event
    world.submission.finished_at = None
    world.db.flush()
    run(world, key)
    assert count(world.db, KnowledgeUnit) == 2
    assert count(world.db, UnitRevision) == 2
    assert count(world.db, Anchor) == 2


def test_ac1_draft_is_a_draft_with_ai_rev0_and_no_question(world: World) -> None:
    # Red when: a draft is written canonical, has no rev 0, or brings a review question.
    run(world)
    units = list(world.db.scalars(select(KnowledgeUnit)))
    assert {u.status for u in units} == {"draft"}
    assert {u.session_id for u in units} == {world.study.id}
    revisions = list(world.db.scalars(select(UnitRevision)))
    assert {(r.rev, r.origin) for r in revisions} == {(0, "ai")}
    assert count(world.db, Question) == 0
    assert world.submission.status == "done" and world.submission.finished_at is not None


def test_section_ids_write_one_row_per_section_primary_first(world: World) -> None:
    # Red when: a section of section_ids is not linked, or the primary is not the first.
    both = [str(world.section.id), str(world.section2.id)]
    run(world, drafts=[world.draft(1, section_ids=both)])
    unit = world.db.scalars(select(KnowledgeUnit)).one()
    rows = list(world.db.scalars(select(UnitSection).order_by(UnitSection.created_at)))
    assert [r.section_id for r in rows] == [world.section.id, world.section2.id]
    assert unit.section_id == world.section.id


def test_foreign_document_and_section_are_dropped_without_error(
    world: World, two_users: tuple[User, User], storage: FakeStorage, db_session: Session
) -> None:
    # Red when: an id of another user's document or section reaches the insert (IntegrityError
    # would send the whole result to the dead letter).
    from sessions.session_helpers import indexed_document, subject_of
    from v2_rows import make_section

    bob = two_users[1]
    other = indexed_document(db_session, storage, bob, subject_of(db_session, bob), sha="ef" * 32)
    foreign_section = make_section(db_session, bob, other)
    bad_doc = world.draft(1)
    bad_doc["anchors"][0]["document_id"] = str(other.id)
    bad_section = world.draft(2, section_id=str(foreign_section.id))
    run(world, drafts=[bad_doc, bad_section, world.draft(3)])
    titles = set(world.db.scalars(select(KnowledgeUnit.title)))
    assert titles == {"Thẻ 2", "Thẻ 3"}
    kept = world.db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.title == "Thẻ 2")).one()
    assert kept.section_id is None
    assert count(world.db, UnitSection) == 1


def test_security_result_key_must_be_the_submissions_own(world: World) -> None:
    # Red when: the key of the event is trusted or only its prefix is compared.
    key = world.put([world.draft(1)])
    other = key.replace("result-", "result-0")
    world.storage.write(other, world.storage.objects[key][0], content_type="x")
    run(world, key=other)
    assert count(world.db, KnowledgeUnit) == 0
    assert world.submission.status == "failed"


def test_security_event_of_another_user_is_ignored(
    world: World, two_users: tuple[User, User]
) -> None:
    # Red when: the session is found by id alone, without the event's user.
    key = world.put([world.draft(1)])
    OnSubmissionProcessed(world.storage)(world.db, world.processed(key, user=two_users[1]))
    assert count(world.db, KnowledgeUnit) == 0
    assert world.submission.status == "processing"


def test_result_naming_another_session_is_refused(world: World) -> None:
    # Red when: the file's own study_session_id is not compared with the locked session.
    body = world.body([world.draft(1)])
    body["study_session_id"] = str(uuid.uuid4())
    import json

    world.storage.write(world.key(), json.dumps(body).encode(), content_type="x")
    run(world, key=world.key())
    assert count(world.db, KnowledgeUnit) == 0
    assert world.submission.status == "failed"


def test_a_late_failure_never_moves_a_done_submission_back(world: World) -> None:
    # Red when: submission.failed after processed changes a done submission.
    run(world)
    on_submission_failed(world.db, world.failed("llm_unavailable"))
    on_submission_failed(world.db, world.failed("internal_error"))
    assert world.submission.status == "done"


def test_ac10_llm_unavailable_parks_the_submission_and_manual_work_stays_open(
    world: World,
) -> None:
    # Red when: llm_unavailable ends the submission as failed (it must wait for quota).
    on_submission_failed(world.db, world.failed("llm_unavailable"))
    assert world.submission.status == "pending_ai"
    assert world.submission.finished_at is None
    on_submission_failed(world.db, world.failed("llm_unavailable"))  # twice: still parked
    assert world.submission.status == "pending_ai"


def test_other_failure_reasons_end_the_submission(world: World) -> None:
    on_submission_failed(world.db, world.failed("unreadable"))
    assert world.submission.status == "failed"
    assert world.submission.finished_at is not None


def test_a_retired_draft_is_not_brought_back_by_a_resent_result(world: World) -> None:
    # Red when: a resent result makes a second card, or revives the retired one.
    key = world.put([world.draft(1)])
    run(world, key)
    unit = world.db.scalars(select(KnowledgeUnit)).one()
    unit.status = "retired"
    from datetime import UTC, datetime

    unit.retired_at = datetime.now(UTC)
    world.submission.status = "processing"
    world.submission.finished_at = None
    world.db.flush()
    run(world, key)
    assert count(world.db, KnowledgeUnit) == 1
    assert unit.status == "retired"
