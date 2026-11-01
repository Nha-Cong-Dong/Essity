"""Edge cases of the `submission_retry` job and of `unit.saved.v1` (T7.8b, US-02b AC9, AC10),
added by the tester: the full retry life cycle with its exact bound and delays, SKIP LOCKED over
two real connections, the exact context key, and the ids carried by `unit.saved.v1`."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from draft_world import NOW, World
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session
from test_submission_retry import park, sent

from accounts import signed_in
from core_api.db.models import KnowledgeUnit, Outbox, Submission, User
from core_api.domain.unit_review import SaveItem, UnitReviewService
from core_api.handlers.session_result_v2 import OnSubmissionProcessed, on_submission_failed
from core_api.jobs.submission_retry import retry_pending_ai
from fake_storage import FakeStorage


@pytest.fixture
def world(db_session: Session, two_users: tuple[User, User]) -> World:
    return World(db_session, two_users[0], FakeStorage())


def test_ac10_life_cycle_six_sends_at_15_30_60_120_240_360_minutes_then_failed(
    world: World,
) -> None:
    # Red when: MAX_RETRIES is not 6, the delay is computed before retry_count is counted (two
    # 15-minute waits), the cap is not 6 h, a row at retry_count == MAX_RETRIES - 1 is not sent,
    # or an exhausted row keeps a next_attempt_at.
    park(world)
    sub = world.submission
    now = NOW
    waits: list[timedelta] = []
    for attempt in range(1, 7):
        counts = retry_pending_ai(world.db, now)
        assert counts == {"retried": 1, "exhausted": 0, "unsendable": 0}, attempt
        assert sub.status == "queued" and sub.retry_count == attempt
        assert sub.next_attempt_at is not None
        waits.append(sub.next_attempt_at - now)
        on_submission_failed(world.db, world.failed("llm_unavailable"))
        assert sub.status == "pending_ai"
        assert retry_pending_ai(world.db, sub.next_attempt_at - timedelta(seconds=1)) == {
            "retried": 0,
            "exhausted": 0,
            "unsendable": 0,
        }
        now = sub.next_attempt_at
    assert waits == [timedelta(minutes=m) for m in (15, 30, 60, 120, 240, 360)]
    assert retry_pending_ai(world.db, now)["exhausted"] == 1
    assert sub.status == "failed" and sub.finished_at == now and sub.next_attempt_at is None
    assert len(sent(world)) == 6
    assert retry_pending_ai(world.db, now + timedelta(days=30))["retried"] == 0


def test_ac10_the_resent_event_has_the_exact_context_key_of_the_submission(world: World) -> None:
    # Red when: the context key differs from the one submissions.py wrote at hand-in
    # (users/<user>/sessions/<session>/context/<submission>.json), so ai-service reads nothing.
    park(world)
    retry_pending_ai(world.db, NOW)
    [event] = sent(world)
    assert event.user_id == world.user.id
    assert event.payload["context_key"] == (
        f"users/{world.user.id}/sessions/{world.study.id}/context/{world.submission.id}.json"
    )
    assert event.payload["study_session_id"] == str(world.study.id)
    assert event.payload["subject_id"] == str(world.subject.id)
    assert [f["object_key"] for f in event.payload["file_keys"]] == world.submission.file_keys


def test_ac10_two_users_parked_each_event_carries_its_own_user(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: one user's resent event carries the other user's id or keys (system job, no
    # request user to lean on).
    storage = FakeStorage()
    alice, bob = World(db_session, two_users[0], storage), World(db_session, two_users[1], storage)
    park(alice)
    park(bob)
    assert retry_pending_ai(db_session, NOW)["retried"] == 2
    events = list(
        db_session.scalars(select(Outbox).where(Outbox.event_type == "submission.created.v1"))
    )
    by_sub = {e.payload["submission_id"]: e for e in events}
    for w in (alice, bob):
        event = by_sub[str(w.submission.id)]
        assert event.user_id == w.user.id
        assert all(
            f["object_key"].startswith(f"users/{w.user.id}/") for f in event.payload["file_keys"]
        )
        assert event.payload["context_key"].startswith(f"users/{w.user.id}/")


@pytest.fixture
def committed_parked(engine: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """A parked submission committed to the database (two real connections need to see it)."""
    with Session(engine, expire_on_commit=False) as setup:
        user, _ = signed_in(setup)
        world = World(setup, user, FakeStorage())
        park(world)
        setup.commit()
        ids = (user.id, world.submission.id)
    try:
        yield ids
    finally:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("DELETE FROM outbox WHERE user_id = :u"), {"u": ids[0]})
            connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": ids[0]})


def test_ac10_a_row_locked_by_another_worker_is_skipped_not_waited_on(
    engine: Engine, committed_parked: tuple[uuid.UUID, uuid.UUID]
) -> None:
    # Red when: the job drops FOR UPDATE (the locked row is sent a second time: retried 1) or
    # SKIP LOCKED (it waits on the lock: lock_timeout error).
    _, submission_id = committed_parked
    with Session(engine) as holder, Session(engine) as worker:
        holder.execute(
            select(Submission).where(Submission.id == submission_id).with_for_update()
        ).one()
        worker.execute(text("SET LOCAL lock_timeout = '2s'"))
        counts = retry_pending_ai(worker, NOW + timedelta(days=1))
        assert counts == {"retried": 0, "exhausted": 0, "unsendable": 0}
        worker.rollback()
        holder.rollback()
    with Session(engine) as again:
        assert retry_pending_ai(again, NOW + timedelta(days=1))["retried"] == 1
        again.rollback()


def test_ac9_unit_saved_carries_the_unit_its_revision_and_its_subject(world: World) -> None:
    # Red when: unit.saved.v1 swaps unit_id/subject_id, carries another revision than the one
    # written, or is written under another user's id.
    key = world.put([world.draft(1), world.draft(2)])
    OnSubmissionProcessed(world.storage)(world.db, world.processed(key))
    units = list(
        world.db.scalars(select(KnowledgeUnit).where(KnowledgeUnit.user_id == world.user.id))
    )
    UnitReviewService(world.db, world.user.id).save(
        world.study.id,
        [SaveItem(unit_id=u.id, version=u.version) for u in units],
        now=NOW,
        tz=ZoneInfo("Asia/Ho_Chi_Minh"),
        day_start_hour=4,
        ranges=[],
    )
    events = list(world.db.scalars(select(Outbox).where(Outbox.event_type == "unit.saved.v1")))
    assert sorted(e.payload["unit_id"] for e in events) == sorted(str(u.id) for u in units)
    for event in events:
        assert event.user_id == world.user.id
        assert event.payload == {
            "unit_id": event.payload["unit_id"],
            "unit_rev": 1,
            "subject_id": str(world.subject.id),
        }
