"""T8.3: the practice schedule through the real tables (ADR-0029; US-16 AC3/AC7/AC10/AC11,
US-06 AC1/AC5/AC7). One log row per grade; the state is the replay of the log."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from core_api.db.models import PracticeLog
from core_api.domain.mastery import PracticeRating, PracticeVerdict
from core_api.domain.scheduling.practice import Attempt, PracticeState, apply, replay_ratings
from core_api.repositories.practice import PracticeLogRepository, PracticeStateRepository
from core_api.services.practice import GradeMismatchError, QuestionNotFoundError, readd, remove
from practice_rows import Practice, day


def ratings(practice: Practice) -> list[int]:
    rows = practice.session.scalars(
        select(PracticeLog.rating)
        .where(PracticeLog.user_id == practice.user.id)
        .order_by(PracticeLog.seq)
    )
    return list(rows)


def stored(practice: Practice, question_id: uuid.UUID) -> PracticeState | None:
    return PracticeStateRepository(practice.session, practice.user.id).state(question_id)


# US-16 lifecycle: a question never attempted has no state; the first attempt creates it.
def test_never_attempted_has_no_state_and_first_attempt_creates_it(practice: Practice) -> None:
    # Red when: a state is made before the first attempt, or the first attempt makes none.
    question = practice.question()
    assert stored(practice, question.id) is None
    done = practice.do(question, "correct", day(0))
    assert stored(practice, question.id) == done.state
    assert done.state.last_verdict == "correct"
    assert done.state.removed_at is None


# US-06 AC7 / US-16 AC7: the stored state equals the pure live path step for step.
def test_stored_state_equals_the_pure_live_path_every_field(practice: Practice) -> None:
    # Red when: the rebuild from the log differs from `apply` in any field (ratings 1,2,3,4).
    question = practice.question()
    chain: list[tuple[PracticeVerdict, float]] = [
        ("incorrect", 100),
        ("correct", 100),
        ("correct", 40),  # Good then Easy: correct, fast, previous correct
        ("partial", 100),
        ("correct", 40),
        ("correct", 40),
    ]
    live: PracticeState | None = None
    for n, (verdict, active) in enumerate(chain):
        at = day(3 * n)
        live = apply(live, Attempt(verdict, active, 100.0, True, at))
        done = practice.do(question, verdict, at, active=active)
        assert done.state == live
    assert PracticeRating.EASY in ratings(practice)
    assert stored(practice, question.id) == live


@pytest.mark.parametrize(
    ("previous", "verdict", "active", "timing_ok", "expected"),
    [
        ("correct", "correct", 70.0, True, 4),  # all four: Easy (boundary 0.7 x ref)
        ("correct", "correct", 70.1, True, 3),  # a little too slow
        ("correct", "correct", 50.0, False, 3),  # not measured
        ("partial", "correct", 50.0, True, 3),  # previous attempt not correct
        ("correct", "partial", 50.0, True, 2),  # not correct now
        ("correct", "incorrect", 50.0, True, 1),
    ],
)
def test_easy_needs_all_four_conditions_through_the_service(
    practice: Practice,
    previous: PracticeVerdict,
    verdict: PracticeVerdict,
    active: float,
    timing_ok: bool,
    expected: int,
) -> None:
    # Red when: one of the four Easy conditions is dropped (US-16 Q-C, ADR-0029).
    question = practice.question()
    practice.do(question, previous, day(0))
    practice.do(question, verdict, day(3), active=active, timing_ok=timing_ok)
    assert ratings(practice)[-1] == expected


def test_first_attempt_is_never_easy(practice: Practice) -> None:
    # Red when: Easy is given with no previous attempt.
    practice.do(practice.question(), "correct", day(0), active=1.0)
    assert ratings(practice) == [3]


def test_hidden_or_slow_attempt_is_never_easy(practice: Practice) -> None:
    # Red when: "not measured" (hidden tab, > 3x reference) can still reach Easy.
    question = practice.question()
    practice.do(question, "correct", day(0))
    practice.do(question, "correct", day(3), active=10.0, timing_ok=False)
    assert ratings(practice)[-1] == 3


def test_a_question_does_not_borrow_another_questions_previous(practice: Practice) -> None:
    # Red when: "previous" is the user's last attempt of any question, not of this one.
    first, second = practice.question(), practice.question()
    practice.do(first, "correct", day(0))
    practice.do(second, "correct", day(1), active=10.0)
    assert ratings(practice)[-1] == 3


# US-16 AC10: a regrade recomputes the schedule at once and equals a replay.
def test_regrade_live_equals_rebuild(practice: Practice) -> None:
    # Red when: the regrade adds a second FSRS step on top of the first instead of replacing it.
    question = practice.question()
    practice.do(question, "correct", day(0))
    second = practice.do(question, "correct", day(3))
    again = practice.grade(second.attempt, "incorrect")
    live = practice.record(question, again, "incorrect", day(3))
    expected = replay_ratings([(PracticeRating.GOOD, day(0)), (PracticeRating.AGAIN, day(3))])
    assert expected is not None
    assert live.memory == expected.memory
    assert live.last_verdict == "incorrect"
    PracticeStateRepository(practice.session, practice.user.id).rebuild()
    assert stored(practice, question.id) == live


def test_regrade_previous_verdict_ignores_the_regraded_attempts_old_grade(
    practice: Practice,
) -> None:
    # Red when: the old grade of the same attempt counts as the "previous" attempt for Easy.
    question = practice.question()
    first = practice.do(question, "correct", day(0))
    regrade = practice.grade(first.attempt, "correct")
    practice.record(question, regrade, "correct", day(0), active=10.0)
    assert ratings(practice) == [3, 3]  # no earlier attempt: Good, not Easy


# US-06 AC7: a grade that arrives late is still in the replay, in the order things happened.
def test_late_grade_appends_and_rebuilds(practice: Practice) -> None:
    # Red when: a grade older than the state's last review raises or is lost.
    question = practice.question()
    practice.do(question, "correct", day(3))
    late = practice.do(question, "incorrect", day(0))
    assert len(ratings(practice)) == 2
    expected = replay_ratings([(PracticeRating.AGAIN, day(0)), (PracticeRating.GOOD, day(3))])
    assert expected is not None
    assert late.state.memory == expected.memory
    assert late.state.memory.last_review == day(3)


def test_same_grade_twice_one_log_row_state_unchanged(practice: Practice) -> None:
    # Red when: a retried grade writes a second log row or moves the schedule again.
    question = practice.question()
    done = practice.do(question, "correct", day(0))
    again = practice.record(question, done.grade, "correct", day(0))
    assert again == done.state
    assert ratings(practice) == [3]
    assert PracticeLogRepository(practice.session, practice.user.id).by_grade(done.grade.id)


def test_grade_of_another_question_is_refused(practice: Practice) -> None:
    # Red when: a grade of question B lands in question A's log.
    first, second = practice.question(), practice.question()
    done = practice.do(second, "correct", day(0))
    with pytest.raises(GradeMismatchError):
        practice.record(first, done.grade, "correct", day(1))
    assert stored(practice, first.id) is None


def test_other_users_question_is_refused(practice: Practice, bobs: Practice) -> None:
    # Red when: another user's question can be practised.
    theirs = bobs.question()
    done = practice.do(practice.question(), "correct", day(0))
    with pytest.raises(QuestionNotFoundError):
        practice.record(theirs, done.grade, "correct", day(1))


# US-16 AC11: take a question out of practice and the schedule stops.
def test_remove_before_any_attempt_is_a_noop(practice: Practice) -> None:
    # Red when: removing a never-attempted question makes a state.
    question = practice.question()
    assert remove(practice.session, practice.user.id, question.id, day(0)) is False
    assert stored(practice, question.id) is None


def test_remove_stops_schedule_keeps_row_and_readd_resumes(practice: Practice) -> None:
    # Red when: remove deletes the row or readd restarts the schedule.
    question = practice.question()
    done = practice.do(question, "correct", day(0))
    assert remove(practice.session, practice.user.id, question.id, day(1)) is True
    removed = stored(practice, question.id)
    assert removed is not None
    assert removed.removed_at == day(1)
    assert removed.due is None
    assert removed.memory == done.state.memory
    assert readd(practice.session, practice.user.id, question.id) is True
    assert stored(practice, question.id) == done.state


def test_attempt_on_removed_question_stays_removed(practice: Practice) -> None:
    # Red when: an attempt on a removed question puts it back or loses removed_at.
    question = practice.question()
    practice.do(question, "correct", day(0))
    remove(practice.session, practice.user.id, question.id, day(1))
    after = practice.do(question, "correct", day(2))
    assert after.state.removed_at == day(1)
    assert len(ratings(practice)) == 2


def test_state_reads_last_verdict_from_the_log(practice: Practice) -> None:
    # Red when: the state read back from the database forgets the last verdict (T9.4 "thuộc").
    question = practice.question()
    practice.do(question, "correct", day(0))
    practice.do(question, "partial", day(3))
    state = stored(practice, question.id)
    assert state is not None
    assert state.last_verdict == "partial"


def test_last_verdict_follows_time_order_not_write_order(practice: Practice) -> None:
    # Red when: last verdict follows the write order, not the time order of the log.
    question = practice.question()
    practice.do(question, "correct", day(3))
    practice.do(question, "incorrect", day(0))
    state = stored(practice, question.id)
    assert state is not None
    assert state.last_verdict == "correct"


def test_wrong_answer_is_due_within_a_day(practice: Practice) -> None:
    # Red when: a wrong answer is not due within a day (US-06 AC2 family) in the stored state.
    done = practice.do(practice.question(), "incorrect", day(0))
    assert done.state.due is not None
    assert done.state.due - day(0) <= timedelta(days=1)
