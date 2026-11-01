"""The retry job of submissions parked as `pending_ai` (T7.8b, US-02b AC10): idempotent, bounded."""

from datetime import timedelta

import pytest
from draft_world import NOW, World
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.db.models import NoteFile, Outbox, User
from core_api.handlers.session_result_v2 import OnSubmissionProcessed, on_submission_failed
from core_api.jobs.submission_retry import MAX_RETRIES, delay_after, retry_pending_ai
from fake_storage import FakeStorage


@pytest.fixture
def world(db_session: Session, two_users: tuple[User, User]) -> World:
    return World(db_session, two_users[0], FakeStorage())


def park(world: World, with_file: bool = True) -> None:
    sha = "a" * 64
    key = f"users/{world.user.id}/sessions/{world.study.id}/notes/{sha}.png"
    if with_file:
        world.db.add(
            NoteFile(
                user_id=world.user.id,
                session_id=world.study.id,
                object_key=key,
                sha256=sha,
                mime="image/png",
                size_bytes=10,
            )
        )
        world.submission.file_keys = [key]
    world.submission.status = "pending_ai"
    world.db.flush()


def sent(world: World) -> list[Outbox]:
    return list(
        world.db.scalars(select(Outbox).where(Outbox.event_type == "submission.created.v1"))
    )


def test_ac10_a_parked_submission_is_sent_again_once(world: World) -> None:
    # Red when: the job does not move pending_ai back to queued with a new created event.
    park(world)
    counts = retry_pending_ai(world.db, NOW)
    assert counts["retried"] == 1
    assert world.submission.status == "queued" and world.submission.retry_count == 1
    [event] = sent(world)
    body = event.payload
    assert body["submission_id"] == str(world.submission.id)
    assert body["file_keys"][0]["mime"] == "image/png"
    assert body["context_key"].endswith(f"/context/{world.submission.id}.json")
    assert world.submission.next_attempt_at == NOW + delay_after(1)


def test_a_repeat_run_does_nothing(world: World) -> None:
    # Red when: running twice sends twice (idempotence).
    park(world)
    retry_pending_ai(world.db, NOW)
    assert retry_pending_ai(world.db, NOW)["retried"] == 0
    assert len(sent(world)) == 1


def test_not_due_yet_waits_then_goes(world: World) -> None:
    # Red when: next_attempt_at is ignored, so a failing model is hammered.
    park(world)
    retry_pending_ai(world.db, NOW)
    on_submission_failed(world.db, world.failed("llm_unavailable"))
    assert world.submission.status == "pending_ai"
    assert retry_pending_ai(world.db, NOW + timedelta(minutes=14))["retried"] == 0
    assert retry_pending_ai(world.db, NOW + timedelta(minutes=15))["retried"] == 1
    assert world.submission.retry_count == 2


def test_the_delay_grows_and_is_capped() -> None:
    assert [delay_after(n) for n in (1, 2, 3)] == [timedelta(minutes=m) for m in (15, 30, 60)]
    assert delay_after(30) == timedelta(hours=6)


def test_ac10_bounded_after_max_retries_it_ends_as_failed(world: World) -> None:
    # Red when: a parked submission is retried for ever.
    park(world)
    world.submission.retry_count = MAX_RETRIES
    world.db.flush()
    counts = retry_pending_ai(world.db, NOW)
    assert counts["exhausted"] == 1 and sent(world) == []
    assert world.submission.status == "failed" and world.submission.finished_at is not None


def test_a_submission_with_no_files_left_ends_as_failed(world: World) -> None:
    park(world, with_file=False)
    assert retry_pending_ai(world.db, NOW)["unsendable"] == 1
    assert world.submission.status == "failed" and sent(world) == []


@pytest.mark.parametrize("status", ["queued", "processing", "done", "failed"])
def test_only_pending_ai_is_taken(world: World, status: str) -> None:
    park(world)
    world.submission.status = status
    if status in {"done", "failed"}:
        world.submission.finished_at = NOW
    world.db.flush()
    assert retry_pending_ai(world.db, NOW) == {"retried": 0, "exhausted": 0, "unsendable": 0}


def test_a_result_that_lands_after_a_retry_is_written_once(world: World) -> None:
    # Red when: the retry plus a late first result makes two cards or revives an ended row.
    park(world)
    retry_pending_ai(world.db, NOW)
    key = world.put([world.draft(1)])
    handler = OnSubmissionProcessed(world.storage)
    handler(world.db, world.processed(key))
    assert world.submission.status == "done"
    handler(world.db, world.processed(key))
    assert retry_pending_ai(world.db, NOW + timedelta(days=1))["retried"] == 0


def test_a_key_without_a_note_row_of_this_session_is_not_sent(world: World) -> None:
    # Red when: file types are looked up by key alone, not by this user's and session's rows.
    park(world, with_file=False)
    sha = "b" * 64
    world.submission.file_keys = [
        f"users/{world.user.id}/sessions/{world.study.id}/notes/{sha}.png"
    ]
    world.db.flush()
    assert retry_pending_ai(world.db, NOW)["unsendable"] == 1
