"""QA2-FSRS tester: edges of "only the last attempt of a learning day counts" (user 04/11). The
learning day is the user's own (timezone + day_start_hour), not UTC and not the calendar date."""

import uuid
from datetime import UTC, datetime, timedelta

from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.practice import replay_ratings
from core_api.repositories.practice import PracticeLogRepository, PracticeStateRepository
from practice_rows import START, Practice, day

# START is 20:00 in Ho Chi Minh City (the default zone), day_start_hour 4.
LOCAL_0330 = START + timedelta(hours=7, minutes=30)  # 03:30 next calendar day, same learning day
LOCAL_0430 = START + timedelta(hours=8, minutes=30)  # 04:30: a new learning day
REDO = timedelta(minutes=5)


def ratings(practice: Practice, question_id: uuid.UUID | None = None) -> list[PracticeRating]:
    log = PracticeLogRepository(practice.session, practice.user.id)
    rows = log.effective(None if question_id is None else [question_id])
    return [r.rating for r in rows]


def test_before_day_start_is_still_the_same_learning_day(practice: Practice) -> None:
    # Red when: the day is the calendar date (day_start_hour ignored): 03:30 opens a new day.
    question = practice.question()
    practice.do(question, "correct", START)
    redo = practice.do(question, "incorrect", LOCAL_0330)
    assert ratings(practice, question.id) == [PracticeRating.AGAIN]
    expected = replay_ratings([(PracticeRating.AGAIN, LOCAL_0330)])
    assert expected is not None and redo.state.memory == expected.memory


def test_day_start_hour_in_the_user_zone_opens_a_new_day(practice: Practice) -> None:
    # Red when: the day is taken in UTC (20:30 and 21:30 UTC share a date) or without the start
    # hour (both are 2 Oct local): 03:30 and 04:30 local are two learning days and both count.
    question = practice.question()
    practice.do(question, "correct", LOCAL_0330)
    later = practice.do(question, "incorrect", LOCAL_0430)
    assert ratings(practice, question.id) == [PracticeRating.GOOD, PracticeRating.AGAIN]
    expected = replay_ratings(
        [(PracticeRating.GOOD, LOCAL_0330), (PracticeRating.AGAIN, LOCAL_0430)]
    )
    assert expected is not None and later.state.memory == expected.memory


def test_the_day_follows_this_user_settings_not_the_default(bobs: Practice) -> None:
    # Red when: day_of uses the default zone/start (or another user's): in Ho Chi Minh at 04:00
    # these two answers share a day, for Bob (New York, day starts 00:00) they do not.
    bobs.user.timezone, bobs.user.day_start_hour = "America/New_York", 0
    bobs.session.flush()
    question = bobs.question()
    late = datetime(2026, 10, 2, 3, 30, tzinfo=UTC)  # 23:30 on 1 Oct in New York
    bobs.do(question, "correct", late)
    bobs.do(question, "incorrect", late + timedelta(hours=1))  # 00:30 on 2 Oct
    assert ratings(bobs, question.id) == [PracticeRating.GOOD, PracticeRating.AGAIN]


def test_dst_end_repeated_hour_stays_one_learning_day(bobs: Practice) -> None:
    # Red when: the learning day is computed from a fixed UTC offset across the DST change.
    # Berlin, 25 Oct 2026: 02:30 CEST (00:30 UTC) and 02:30 CET (01:30 UTC) are both before the
    # 03:00 start, so 24 Oct; 03:30 CET (02:30 UTC) is 25 Oct.
    bobs.user.timezone, bobs.user.day_start_hour = "Europe/Berlin", 3
    bobs.session.flush()
    question = bobs.question()
    first = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    bobs.do(question, "correct", first)
    bobs.do(question, "partial", first + timedelta(hours=1))
    bobs.do(question, "incorrect", first + timedelta(hours=2))
    assert ratings(bobs, question.id) == [PracticeRating.HARD, PracticeRating.AGAIN]


def test_a_late_grade_of_an_earlier_same_day_try_does_not_win(practice: Practice) -> None:
    # Red when: "last" means last graded instead of last submitted: the first try, graded after
    # the redo, takes over the schedule.
    question = practice.question()
    first = practice.attempt(question, day(0))
    redo = practice.attempt(question, day(0) + REDO)
    after_redo = practice.record(question, practice.grade(redo, "incorrect"), "incorrect")
    after_late = practice.record(question, practice.grade(first, "correct"), "correct")
    assert after_late == after_redo
    assert ratings(practice, question.id) == [PracticeRating.AGAIN]
    states = PracticeStateRepository(practice.session, practice.user.id)
    states.rebuild([question.id])
    assert states.state(question.id) == after_redo


def test_easy_looks_at_the_last_try_of_the_earlier_day(practice: Practice) -> None:
    # Red when: "previous" is the first try of the earlier day (correct) instead of its last
    # (incorrect): a fast correct answer the next day would be Easy.
    question = practice.question()
    practice.do(question, "correct", day(0))
    practice.do(question, "incorrect", day(0) + REDO)
    practice.do(question, "correct", day(1), active=10.0)
    assert ratings(practice, question.id) == [PracticeRating.AGAIN, PracticeRating.GOOD]


def test_easy_after_a_corrected_earlier_day(practice: Practice) -> None:
    # Red when: a wrong first try that a same-day redo fixed still blocks Easy the next day.
    question = practice.question()
    practice.do(question, "incorrect", day(0))
    practice.do(question, "correct", day(0) + REDO)
    practice.do(question, "correct", day(1), active=10.0)
    assert ratings(practice, question.id) == [PracticeRating.GOOD, PracticeRating.EASY]


def test_many_tries_over_two_days_keep_one_per_day(practice: Practice) -> None:
    # Red when: the replacement only looks one row back, or a day keeps its first try.
    question = practice.question()
    for n, verdict in enumerate(("correct", "incorrect", "partial")):
        practice.do(question, verdict, day(0) + n * REDO)
    for n, verdict in enumerate(("partial", "correct")):
        practice.do(question, verdict, day(2) + n * REDO)
    assert ratings(practice, question.id) == [PracticeRating.HARD, PracticeRating.GOOD]


def test_two_questions_on_the_same_day_do_not_replace_each_other(practice: Practice) -> None:
    # Red when: the day collapse runs over the whole log, not per question: one question's
    # answer replaces another's, and the rebuild loses a question's schedule.
    one, two = practice.question(), practice.question()
    practice.do(one, "incorrect", day(0))
    practice.do(two, "correct", day(0) + REDO)
    rows = PracticeLogRepository(practice.session, practice.user.id).effective()
    assert {(r.question_id, r.rating) for r in rows} == {
        (one.id, PracticeRating.AGAIN),
        (two.id, PracticeRating.GOOD),
    }
    states = PracticeStateRepository(practice.session, practice.user.id)
    assert states.rebuild() == 2


def test_another_users_redo_does_not_touch_my_day(practice: Practice, bobs: Practice) -> None:
    # Red when: the effective log or its day lookup mixes the two users' rows.
    mine, his = practice.question(), bobs.question()
    practice.do(mine, "correct", day(0))
    bobs.do(his, "incorrect", day(0) + REDO)
    assert ratings(practice) == [PracticeRating.GOOD]
    assert ratings(bobs) == [PracticeRating.AGAIN]
