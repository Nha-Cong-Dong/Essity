"""T8.3 tester: edge cases the lane tests leave open (ADR-0029; US-16 AC3/AC7/AC10, US-06 AC7).
The learning-day end across a DST change, "thuộc" read back from the database, an empty rebuild."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from core_api.cli import run
from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.practice import is_known
from core_api.repositories.practice import PracticeLogRepository, PracticeStateRepository
from core_api.services.practice import remove
from practice_rows import Practice, day


def _due_ids(practice: Practice, on: date) -> set[object]:
    repo = PracticeStateRepository(practice.session, practice.user.id)
    return {row.question_id for row in repo.due_on(on)}


# Study-day boundary across DST (plan Y5): the day is 25 or 23 hours long, never "start + 24 h".
@pytest.mark.parametrize(
    ("on", "due_utc", "is_due"),
    [
        # 31 Oct 2026, New York: starts 04:00 EDT (08:00 UTC), DST ends overnight, so the day
        # ends 04:00 EST on 1 Nov = 09:00 UTC (25 hours).
        (date(2026, 10, 31), datetime(2026, 11, 1, 8, 30, tzinfo=UTC), True),
        (date(2026, 10, 31), datetime(2026, 11, 1, 9, 0, tzinfo=UTC), False),
        # 13 Mar 2027: starts 04:00 EST (09:00 UTC), DST starts overnight, so the day ends
        # 04:00 EDT on 14 Mar = 08:00 UTC (23 hours).
        (date(2027, 3, 13), datetime(2027, 3, 14, 7, 59, tzinfo=UTC), True),
        (date(2027, 3, 13), datetime(2027, 3, 14, 8, 30, tzinfo=UTC), False),
    ],
)
def test_due_on_learning_day_end_across_dst(
    practice: Practice, on: date, due_utc: datetime, is_due: bool
) -> None:
    # Red when: due_on ends the day at start + 24 h, at a fixed UTC offset, or in UTC.
    practice.user.timezone = "America/New_York"
    practice.user.day_start_hour = 4
    question = practice.question()
    practice.do(question, "correct", day(0))
    row = PracticeStateRepository(practice.session, practice.user.id).row(question.id)
    assert row is not None
    row.due = due_utc
    practice.session.flush()
    assert (question.id in _due_ids(practice, on)) is is_due


# PLAN T8.3 "thuộc" (used by T9.4): the pure is_known on the state read back from the database.
def test_is_known_on_the_stored_state_needs_recall_and_last_correct(practice: Practice) -> None:
    # Red when: the stored state loses last_verdict, or is_known ignores recall or the verdict.
    question = practice.question()
    practice.do(question, "correct", day(0))
    last = practice.do(question, "correct", day(3))
    practice.session.expire_all()
    repo = PracticeStateRepository(practice.session, practice.user.id)
    state = repo.state(question.id)
    assert state is not None
    assert state.memory.last_review == day(3)
    assert is_known(state, day(3) + timedelta(hours=1)) is True
    assert is_known(state, day(3) + timedelta(days=3650)) is False  # recall has faded
    # US-16 AC10: a regrade of the last attempt to wrong makes it not "thuộc" at once.
    regrade = practice.grade(last.attempt, "incorrect")
    practice.record(question, regrade, "incorrect")
    practice.session.expire_all()
    after = repo.state(question.id)
    assert after is not None
    assert after.last_verdict == "incorrect"
    assert is_known(after, day(3) + timedelta(hours=1)) is False


def test_is_known_false_when_the_last_stored_attempt_is_partial(practice: Practice) -> None:
    # Red when: "Đúng một phần" read from the log counts as correct for "thuộc".
    question = practice.question()
    practice.do(question, "correct", day(0))
    practice.do(question, "partial", day(3))
    practice.session.expire_all()
    state = PracticeStateRepository(practice.session, practice.user.id).state(question.id)
    assert state is not None
    assert is_known(state, day(3) + timedelta(minutes=1)) is False


# Empty: a user with no practice log at all.
def test_rebuild_with_no_log_writes_nothing(
    db_session: Session, practice: Practice, capsys: pytest.CaptureFixture[str]
) -> None:
    # Red when: an empty log makes a state row, or the CLI fails on a user with no practice.
    practice.question()
    repo = PracticeStateRepository(practice.session, practice.user.id)
    assert repo.rebuild() == 0
    assert repo.rebuild([]) == 0
    assert run(db_session, ["rebuild-practice-state", "--user-email", "alice@example.com"]) == 0
    assert "rebuilt 0 practice states" in capsys.readouterr().out
    assert repo.list() == []


def test_rebuild_of_one_question_leaves_the_others_and_their_removal(practice: Practice) -> None:
    # Red when: rebuild([q]) drops or rewrites another question's row or its removed_at.
    first, second = practice.question(), practice.question()
    practice.do(first, "correct", day(0))
    practice.do(second, "incorrect", day(0))
    remove(practice.session, practice.user.id, second.id, day(1))
    repo = PracticeStateRepository(practice.session, practice.user.id)
    before = repo.state(second.id)
    assert repo.rebuild([first.id]) == 1
    assert repo.state(second.id) == before
    assert before is not None
    assert before.removed_at == day(1)


# US-16 AC7, "lần trước của chính câu đó": a grade that arrives late looks back in time only.
def test_late_grade_does_not_take_a_later_attempt_as_its_previous(practice: Practice) -> None:
    # Red when: "previous" for a late grade is an attempt made after it, so it can reach Easy.
    question = practice.question()
    practice.do(question, "correct", day(3))
    practice.do(question, "correct", day(0), active=10.0)
    log = PracticeLogRepository(practice.session, practice.user.id).effective([question.id])
    assert [(r.reviewed_at, r.rating) for r in log] == [
        (day(0), PracticeRating.GOOD),  # first in time: no previous, never Easy
        (day(3), PracticeRating.GOOD),
    ]
