"""CARDS-V3 tester edges: the result handler that sends cards straight to the vault.

A later result of the same session must promote only the cards it made, and the learning day of a
card is the learner's, not UTC's."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from draft_world import World
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.db.models import KnowledgeUnit, Submission, User
from core_api.domain.unit_review import saved_learning_day
from core_api.handlers.session_result_v2 import OnSubmissionProcessed
from fake_storage import FakeStorage


@pytest.fixture
def world(db_session: Session, two_users: tuple[User, User]) -> World:
    return World(db_session, two_users[0], FakeStorage())


def test_a_new_result_never_revives_a_card_the_learner_deleted(world: World) -> None:
    # Red when: the handler promotes every card of the session instead of the ones it just wrote,
    # so a card the learner deleted in the Kho (retired) comes back with the next result.
    key = world.put([world.draft(1)])
    OnSubmissionProcessed(world.storage)(world.db, world.processed(key))
    gone = world.db.scalars(select(KnowledgeUnit)).one()
    gone.status, gone.retired_at = "retired", datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
    world.db.flush()
    world.submission = Submission(
        user_id=world.user.id, session_id=world.study.id, status="processing", file_keys=[]
    )
    world.db.add(world.submission)
    world.db.flush()
    key = world.put([world.draft(2)])
    OnSubmissionProcessed(world.storage)(world.db, world.processed(key))
    world.db.refresh(gone)
    assert gone.status == "retired" and gone.retired_at is not None
    statuses = {u.title: u.status for u in world.db.scalars(select(KnowledgeUnit))}
    assert statuses == {"Thẻ 1": "retired", "Thẻ 2": "canonical"}


def test_card_learning_day_is_the_learners_not_utc(world: World) -> None:
    # Red when: the card is dated by UTC (or the server's zone): 20:00 UTC is already the next
    # day in Ho Chi Minh, so it would land on the wrong day of the ledger and the schedule.
    world.user.timezone, world.user.day_start_hour = "Asia/Ho_Chi_Minh", 0
    world.db.flush()
    at = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)
    learner = saved_learning_day(at, ZoneInfo("Asia/Ho_Chi_Minh"), 0)
    assert learner != saved_learning_day(at, ZoneInfo("UTC"), 0)  # the case is a real boundary
    key = world.put([world.draft(1)])
    OnSubmissionProcessed(world.storage)(world.db, world.processed(key, at=at))
    unit = world.db.scalars(select(KnowledgeUnit)).one()
    assert unit.status == "canonical" and unit.saved_learning_day == learner
