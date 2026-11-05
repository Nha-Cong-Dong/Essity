"""QA2-FSRS (N3, user decision 04/11 "tính fsrs dựa vào lần cuối cùng làm lại"): when a practice
question is answered again on the same learning day ("Làm lại câu này"), only the last attempt of
that day moves the FSRS schedule; the earlier ones stay in `practice_log` but do not count. A
regrade ("Chấm sai") already replaces its attempt's rating (latest grade per attempt)."""

from datetime import timedelta

from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.practice import replay_ratings
from core_api.repositories.practice import PracticeLogRepository, PracticeStateRepository
from practice_rows import Practice, day

REDO = timedelta(minutes=5)


def test_redo_same_day_schedule_follows_the_last_attempt_only(practice: Practice) -> None:
    # Red when: both attempts are stepped (Good then Again), as QA saw: relearning S 0.78.
    question = practice.question()
    practice.do(question, "correct", day(0))
    redo = practice.do(question, "incorrect", day(0) + REDO)
    expected = replay_ratings([(PracticeRating.AGAIN, day(0) + REDO)])
    assert expected is not None
    assert redo.state.memory == expected.memory
    assert redo.state.last_verdict == "incorrect"
    log = PracticeLogRepository(practice.session, practice.user.id)
    assert [r.rating for r in log.effective([question.id])] == [PracticeRating.AGAIN]
    PracticeStateRepository(practice.session, practice.user.id).rebuild()
    assert PracticeStateRepository(practice.session, practice.user.id).state(question.id) == (
        redo.state
    )


def test_redo_wrong_then_right_counts_as_right(practice: Practice) -> None:
    # Red when: the wrong first try still drags the schedule after a correct redo.
    question = practice.question()
    practice.do(question, "incorrect", day(0))
    redo = practice.do(question, "correct", day(0) + REDO)
    expected = replay_ratings([(PracticeRating.GOOD, day(0) + REDO)])
    assert expected is not None
    assert redo.state.memory == expected.memory


def test_redo_previous_for_easy_is_the_last_counted_earlier_day(practice: Practice) -> None:
    # Red when: a same-day first try counts as the "previous correct" that unlocks Easy.
    question = practice.question()
    practice.do(question, "correct", day(0))
    redo = practice.do(question, "correct", day(0) + REDO, active=10.0)
    expected = replay_ratings([(PracticeRating.GOOD, day(0) + REDO)])
    assert expected is not None
    assert redo.state.memory == expected.memory  # Good, not Easy: nothing counted before today


def test_attempts_on_different_days_still_stack(practice: Practice) -> None:
    # Red when: the collapse merges attempts of different learning days.
    question = practice.question()
    practice.do(question, "correct", day(0))
    later = practice.do(question, "incorrect", day(3))
    expected = replay_ratings([(PracticeRating.GOOD, day(0)), (PracticeRating.AGAIN, day(3))])
    assert expected is not None
    assert later.state.memory == expected.memory


def test_regrade_of_the_redo_replaces_it(practice: Practice) -> None:
    # Red when: a regrade of the last same-day attempt does not decide the schedule.
    question = practice.question()
    practice.do(question, "correct", day(0))
    redo = practice.do(question, "incorrect", day(0) + REDO)
    fixed = practice.grade(redo.attempt, "correct")
    live = practice.record(question, fixed, "correct")
    expected = replay_ratings([(PracticeRating.GOOD, day(0) + REDO)])
    assert expected is not None
    assert live.memory == expected.memory
    assert live.last_verdict == "correct"


def test_regrade_of_the_superseded_first_try_does_not_move_the_schedule(
    practice: Practice,
) -> None:
    # Red when: regrading an attempt that a same-day redo replaced changes the schedule.
    question = practice.question()
    first = practice.do(question, "correct", day(0))
    redo = practice.do(question, "incorrect", day(0) + REDO)
    fixed = practice.grade(first.attempt, "incorrect")
    live = practice.record(question, fixed, "incorrect")
    assert live == redo.state
