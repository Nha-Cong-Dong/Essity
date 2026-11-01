"""T8.4 repository of practice attempts (US-16 AC2/AC5; T7.M5 review: two concurrent opens).
`served_at` is the server's and written once; the submit UPDATE writes and freezes the timing; a
review attempt and a practice attempt never see each other; another user's attempt is not found."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from core_api.db.models import Attempt
from core_api.repositories.practice_attempt import (
    AttemptNotDraftError,
    AttemptNotFoundError,
    PracticeAttemptRepository,
    QuestionNotFoundError,
)
from core_api.repositories.user import UserRepository
from practice_rows import Practice
from races import finished, in_thread, wait_for_lock

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def test_open_makes_one_draft_with_server_served_at(
    practice: Practice, db_session: Session
) -> None:
    # Red when: served_at is missing or the second open makes a second draft or moves served_at.
    question = practice.question()
    repo = PracticeAttemptRepository(db_session, practice.user.id)
    first, made = repo.open_draft(question.id, NOW)
    again, made_again = repo.open_draft(question.id, NOW + timedelta(minutes=5))
    assert (made, made_again) == (True, False)
    assert again.id == first.id
    assert again.served_at == NOW


def test_open_is_refused_for_another_users_question(
    practice: Practice, bobs: Practice, db_session: Session
) -> None:
    # Red when: a question of another user can be opened (ADR-0014: not found, not forbidden).
    question = bobs.question()
    with pytest.raises(QuestionNotFoundError):
        PracticeAttemptRepository(db_session, practice.user.id).open_draft(question.id, NOW)


def test_submit_writes_timing_once_and_freezes(practice: Practice, db_session: Session) -> None:
    # Red when: the timing is not in the submit UPDATE, or a second submit changes it.
    question = practice.question()
    repo = PracticeAttemptRepository(db_session, practice.user.id)
    attempt, _ = repo.open_draft(question.id, NOW)
    done = repo.submit(
        attempt.id,
        NOW + timedelta(seconds=90),
        hidden_ms=0,
        reference_seconds=60.0,
        answer_text="câu trả lời",
    )
    assert (done.status, done.hidden_ms, done.active_ms, done.timing_ok) == (
        "submitted",
        0,
        90_000,
        True,
    )
    assert done.answer_text == "câu trả lời"
    with pytest.raises(AttemptNotDraftError):
        repo.submit(attempt.id, NOW + timedelta(hours=1), hidden_ms=0, reference_seconds=60.0)
    with pytest.raises(DBAPIError, match="is refused"), db_session.begin_nested():
        db_session.execute(
            text("UPDATE attempt SET active_ms = 1 WHERE id = :a"), {"a": attempt.id}
        )


def test_submit_slow_or_hidden_is_not_timing_ok(practice: Practice, db_session: Session) -> None:
    # Red when: the 3x rule or the hidden rule is not applied at submit.
    repo = PracticeAttemptRepository(db_session, practice.user.id)
    slow, _ = repo.open_draft(practice.question().id, NOW)
    hidden, _ = repo.open_draft(practice.question().id, NOW)
    slowed = repo.submit(slow.id, NOW + timedelta(seconds=181), hidden_ms=0, reference_seconds=60.0)
    assert not slowed.timing_ok
    done = repo.submit(
        hidden.id, NOW + timedelta(seconds=30), hidden_ms=5_000, reference_seconds=60.0
    )
    assert (done.hidden_ms, done.active_ms, done.timing_ok) == (5_000, 25_000, False)


def test_save_draft_then_not_after_submit(practice: Practice, db_session: Session) -> None:
    # Red when: a draft cannot be saved, or a submitted attempt can.
    repo = PracticeAttemptRepository(db_session, practice.user.id)
    attempt, _ = repo.open_draft(practice.question().id, NOW)
    repo.save_draft(attempt.id, answer_text="nháp", dont_remember=False)
    repo.submit(attempt.id, NOW, hidden_ms=0, reference_seconds=60.0)
    with pytest.raises(AttemptNotDraftError):
        repo.save_draft(attempt.id, answer_text="x", dont_remember=False)


def test_other_user_and_review_attempts_are_not_found(
    practice: Practice, bobs: Practice, db_session: Session
) -> None:
    # Red when: another user's practice attempt, or a review attempt, shows in this repository.
    mine, _ = PracticeAttemptRepository(db_session, practice.user.id).open_draft(
        practice.question().id, NOW
    )
    bob_repo = PracticeAttemptRepository(db_session, bobs.user.id)
    assert bob_repo.get_practice(mine.id) is None
    with pytest.raises(AttemptNotFoundError):
        bob_repo.save_draft(mine.id, answer_text="x", dont_remember=False)
    with pytest.raises(AttemptNotFoundError):
        bob_repo.submit(mine.id, NOW, hidden_ms=0, reference_seconds=60.0)
    reviewed = practice.question()
    practice.attempt(reviewed, NOW)
    review_attempt = db_session.scalars(
        select(Attempt).where(Attempt.question_id == reviewed.id)
    ).one()
    mine_repo = PracticeAttemptRepository(db_session, practice.user.id)
    assert mine_repo.get_practice(review_attempt.id) is None


# --- two real connections ----------------------------------------------------------------------


@pytest.fixture
def committed(engine: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t84-draft-{uuid.uuid4()}@example.com")
        session.flush()
        question = Practice(session, user).question()
        ids = (user.id, question.id)
        session.commit()
    yield ids
    with engine.begin() as connection:
        names = list(
            connection.execute(
                text(
                    "SELECT DISTINCT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid ="
                    " t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " WHERE NOT t.tgisinternal AND n.nspname = 'public'"
                )
            ).scalars()
        )
        for name in names:
            connection.execute(text(f'ALTER TABLE "{name}" DISABLE TRIGGER USER'))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": ids[0]})
        for name in names:
            connection.execute(text(f'ALTER TABLE "{name}" ENABLE TRIGGER USER'))


def test_two_concurrent_opens_make_one_draft(
    engine: Engine, committed: tuple[uuid.UUID, uuid.UUID]
) -> None:
    # Red when: two requests opening the same question at once make two drafts or raise
    # IntegrityError (T7.M5 review; US-16 AC2). B waits on A's uncommitted insert, then reads it.
    user_id, question_id = committed
    first = Session(engine)
    second = Session(engine)
    try:
        a, made_a = PracticeAttemptRepository(first, user_id).open_draft(question_id, NOW)
        pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(
            lambda: PracticeAttemptRepository(second, user_id).open_draft(
                question_id, NOW + timedelta(seconds=7)
            )
        )
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        assert not isinstance(result, BaseException), result
        b, made_b = cast("tuple[Attempt, bool]", result)
        second.commit()
        assert (made_a, made_b) == (True, False)
        assert a.id == b.id
        assert b.served_at == NOW
        with Session(engine) as check:
            count = check.scalar(
                select(func.count()).select_from(Attempt).where(Attempt.question_id == question_id)
            )
        assert count == 1
    finally:
        first.close()
        second.close()
