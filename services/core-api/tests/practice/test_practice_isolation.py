"""T8.3: the two schedules never touch each other, practice_log only grows, and two users never
see each other's practice rows (ADR-0029, ADR-0024, ADR-0013; US-16 AC3, US-06 AC5)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from core_api.db.models import MemoryState, PracticeLog, ReviewLog
from core_api.domain.scheduling.rating import ReviewRating
from core_api.repositories.base import AppendOnlyError
from core_api.repositories.practice import PracticeLogRepository, PracticeStateRepository
from core_api.repositories.review import MemoryStateRepository, ReviewLogRepository
from practice_rows import Practice, day


def card_rows(session: Session) -> tuple[int, int]:
    return (
        session.query(ReviewLog).count(),
        session.query(MemoryState).count(),
    )


# US-16 AC3 / PLAN T8.3 "Xong khi" (1), direction 1: practising never writes the card schedule.
def test_practice_grade_leaves_review_log_and_memory_state_untouched(practice: Practice) -> None:
    # Red when: record_grade writes review_log or memory_state.
    question = practice.question()
    before = card_rows(practice.session)
    practice.do(question, "correct", day(0))
    practice.do(question, "incorrect", day(3))
    assert card_rows(practice.session) == before == (0, 0)


# Direction 2: grading a card review never writes the practice schedule.
def test_card_review_leaves_practice_state_and_log_untouched(practice: Practice) -> None:
    # Red when: a card review (review_log + memory_state) changes practice_state or practice_log.
    question = practice.question()
    attempt = practice.attempt(question, day(0))
    grade = practice.grade(attempt, "correct")
    unit_id = practice.unit_of(question)
    ReviewLogRepository(practice.session, practice.user.id).append(
        unit_id, rating=ReviewRating.GOOD, reviewed_at=day(0), grade_id=grade.id
    )
    MemoryStateRepository(practice.session, practice.user.id).rebuild()
    assert card_rows(practice.session) == (1, 1)
    assert practice.session.query(PracticeLog).count() == 0
    assert PracticeStateRepository(practice.session, practice.user.id).list() == []


def test_card_rebuild_does_not_touch_an_existing_practice_state(practice: Practice) -> None:
    # Red when: rebuilding the card cache deletes or rewrites practice_state.
    question = practice.question()
    done = practice.do(question, "correct", day(0))
    MemoryStateRepository(practice.session, practice.user.id).rebuild()
    assert PracticeStateRepository(practice.session, practice.user.id).state(question.id) == (
        done.state
    )


# ADR-0024: practice_log is append-only, in the repository and in the database.
def test_practice_log_repo_delete_raises_append_only(practice: Practice) -> None:
    # Red when: the repository allows deleting a log row.
    done = practice.do(practice.question(), "correct", day(0))
    log = PracticeLogRepository(practice.session, practice.user.id)
    row = log.by_grade(done.grade.id)
    assert row is not None
    with pytest.raises(AppendOnlyError):
        log.delete(row.id)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE practice_log SET rating = 1",
        "DELETE FROM practice_log",
        "TRUNCATE practice_log",
    ],
)
def test_practice_log_trigger_refuses_update_delete_truncate(practice: Practice, sql: str) -> None:
    # Red when: the 0025 trigger is missing, so a log row can change or go (ADR-0024).
    practice.do(practice.question(), "correct", day(0))
    with pytest.raises(DBAPIError, match="is refused"), practice.session.begin_nested():
        practice.session.execute(text(sql))
    assert practice.session.query(PracticeLog).count() == 1


# ADR-0013: every read is scoped to the user.
def test_repository_never_reads_other_users_state_or_log(
    practice: Practice, bobs: Practice
) -> None:
    # Red when: Alice's repositories return Bob's question state or log rows.
    theirs = bobs.question()
    done = bobs.do(theirs, "correct", day(0))
    states = PracticeStateRepository(practice.session, practice.user.id)
    log = PracticeLogRepository(practice.session, practice.user.id)
    assert states.state(theirs.id) is None
    assert states.row(theirs.id) is None
    assert states.list() == []
    assert log.by_grade(done.grade.id) is None
    assert log.effective() == []
    assert log.effective([theirs.id]) == []
    assert states.set_removed_at(theirs.id, day(1)) is False
    assert PracticeStateRepository(bobs.session, bobs.user.id).state(theirs.id) is not None


def test_two_users_have_their_own_schedule_for_their_own_questions(
    practice: Practice, bobs: Practice
) -> None:
    # Red when: one user's attempts leak into the other's rebuilt state.
    mine, theirs = practice.question(), bobs.question()
    practice.do(mine, "incorrect", day(0))
    bobs.do(theirs, "correct", day(0))
    assert PracticeStateRepository(practice.session, practice.user.id).state(mine.id)
    assert PracticeStateRepository(bobs.session, bobs.user.id).state(mine.id) is None
    ours = PracticeStateRepository(bobs.session, bobs.user.id).state(theirs.id)
    assert ours is not None
    assert ours.last_verdict == "correct"
