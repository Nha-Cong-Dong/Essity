"""T2.7 (US-03 AC3–AC6, ARCH §5.3): the pure function that composes today's session."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import day_bounds
from core_api.domain.scheduling.fsrs_adapter import MemoryState, Phase
from core_api.domain.today import (
    MAX_MINUTES,
    MAX_QUESTIONS,
    MINUTES_PER_QUESTION,
    DueUnit,
    NewQuestion,
    TodayPlan,
    compose_today,
)

HCM = ZoneInfo("Asia/Ho_Chi_Minh")
DAY_START = 4
TODAY = date(2026, 11, 2)
NOW = datetime.combine(TODAY, time(20), tzinfo=HCM).astimezone(UTC)
MMT, HDH = uuid.uuid4(), uuid.uuid4()


def state(stability: float, last_days_ago: int, due_days: int = 0) -> MemoryState:
    """A unit last reviewed `last_days_ago` days ago, due `due_days` from today's start."""
    start = day_bounds(TODAY, HCM, DAY_START)[0]
    return MemoryState(
        phase=Phase.REVIEW,
        step=None,
        stability=stability,
        difficulty=5.0,
        due=start + timedelta(days=due_days),
        last_review=NOW - timedelta(days=last_days_ago),
    )


def due(subject: uuid.UUID, stability: float = 10.0, last_days_ago: int = 10, **kw: int) -> DueUnit:
    return DueUnit(
        unit_id=uuid.uuid4(),
        subject_id=subject,
        question_id=uuid.uuid4(),
        state=state(stability, last_days_ago, **kw),
    )


def new(subject: uuid.UUID, created_days_ago: int = 1) -> NewQuestion:
    return NewQuestion(
        question_id=uuid.uuid4(),
        subject_id=subject,
        created_at=NOW - timedelta(days=created_days_ago),
    )


def compose(
    units: list[DueUnit],
    fresh: list[NewQuestion] | None = None,
    exams: dict[uuid.UUID, date] | None = None,
) -> TodayPlan:
    exams = exams or {MMT: TODAY + timedelta(days=60), HDH: TODAY + timedelta(days=60)}
    return compose_today(units, fresh or [], exams, now=NOW, tz=HCM, day_start_hour=DAY_START)


# AC3 (1). Red when: due units are taken in storage order instead of by risk of forgetting.
def test_ac3_the_unit_most_likely_forgotten_comes_first() -> None:
    safe = due(MMT, stability=30, last_days_ago=2)
    shaky = due(MMT, stability=2, last_days_ago=20)
    plan = compose([safe, shaky])
    assert [item.question_id for item in plan.items] == [shaky.question_id, safe.question_id]


# AC3, two subjects, one exam close. Red when: the exam's closeness does not weigh in.
def test_ac3_with_equal_risk_the_subject_whose_exam_is_close_comes_first() -> None:
    far, near = due(MMT), due(HDH)
    plan = compose([far, near], exams={MMT: TODAY + timedelta(days=60), HDH: TODAY + timedelta(3)})
    assert plan.items[0].question_id == near.question_id


# Q5. Red when: one subject's many risky units crowd another subject out of the session.
def test_q5_no_subject_is_starved() -> None:
    crowd = [due(MMT, stability=1, last_days_ago=30) for _ in range(40)]
    lone = due(HDH, stability=50, last_days_ago=1)
    plan = compose([*crowd, lone])
    assert lone.question_id in {item.question_id for item in plan.items}


# AC3 (2). Red when: new questions are left out though there is room, or the oldest come first.
def test_ac3_room_left_is_filled_with_the_newest_questions() -> None:
    old, recent = new(MMT, created_days_ago=30), new(MMT, created_days_ago=1)
    plan = compose([due(MMT)], [old, recent])
    assert [item.question_id for item in plan.items[1:]] == [recent.question_id, old.question_id]
    assert [item.kind for item in plan.items] == ["due", "new", "new"]


# AC4. Red when: the cap is missing or counted wrong.
def test_ac4_a_session_stops_at_20_questions_and_30_minutes() -> None:
    plan = compose([due(MMT) for _ in range(30)], [new(MMT) for _ in range(10)])
    assert len(plan.items) == MAX_QUESTIONS
    assert plan.minutes <= MAX_MINUTES
    assert plan.minutes == round(MAX_QUESTIONS * MINUTES_PER_QUESTION)


def test_ac4_units_not_yet_due_today_wait() -> None:
    tomorrow = due(MMT, due_days=1)
    plan = compose([tomorrow])
    assert plan.items == []
    assert plan.next_day == TODAY + timedelta(days=1)


# One question can check several units: it is asked once.
def test_a_question_checking_two_due_units_is_asked_once() -> None:
    a, b = due(MMT), due(MMT)
    shared = DueUnit(unit_id=b.unit_id, subject_id=MMT, question_id=a.question_id, state=b.state)
    plan = compose([a, shared])
    assert [item.question_id for item in plan.items] == [a.question_id]


# AC5: a backlog of 200 units. Red when: the session grows past the cap, or no neutral note
# comes back when the exam is too close to get through it.
def test_ac5_a_backlog_of_200_keeps_the_cap_and_says_how_many_sessions_it_needs() -> None:
    backlog = [due(MMT) for _ in range(200)]
    plan = compose(backlog, exams={MMT: TODAY + timedelta(days=5)})
    assert len(plan.items) == MAX_QUESTIONS
    assert plan.backlog is not None
    assert (plan.backlog.subject_id, plan.backlog.sessions, plan.backlog.days) == (MMT, 10, 5)


def test_ac5_no_note_when_the_backlog_fits_before_the_exam() -> None:
    plan = compose([due(MMT) for _ in range(200)], exams={MMT: TODAY + timedelta(days=30)})
    assert plan.backlog is None


# AC6. Red when: nothing due gives an empty answer with no next day to show.
def test_ac6_nothing_due_and_nothing_new_says_when_the_next_session_is() -> None:
    plan = compose([due(MMT, due_days=3), due(HDH, due_days=5)])
    assert plan.items == []
    assert plan.next_day == TODAY + timedelta(days=3)


def test_ac6_no_units_at_all_has_no_next_day() -> None:
    plan = compose([])
    assert plan.items == [] and plan.next_day is None and plan.backlog is None


# Review PR #20 🟡1. Red when: on the exam day the weight jumps back to that of no exam, so a
# subject examined in three days goes before the one examined today.
def test_ac3_the_exam_today_comes_before_an_exam_in_three_days() -> None:
    later, today = due(HDH), due(MMT)
    plan = compose([later, today], exams={MMT: TODAY, HDH: TODAY + timedelta(days=3)})
    assert plan.items[0].question_id == today.question_id


# Review PR #20 🟡2. Red when: the backlog is judged subject by subject, though every subject
# shares one session a day (AC7): three subjects that each fit can together overflow.
def test_ac5_subjects_sharing_the_days_before_their_exams_add_up() -> None:
    third = uuid.uuid4()
    units = [due(s) for s in (MMT, HDH, third) for _ in range(90)]
    exam = TODAY + timedelta(days=5)
    plan = compose(units, exams={MMT: exam, HDH: exam, third: exam})
    assert plan.backlog is not None
    assert (plan.backlog.sessions, plan.backlog.days) == (14, 5)


def test_minutes_round_up() -> None:
    assert compose([due(MMT)]).minutes == 2
    assert compose([due(MMT) for _ in range(3)]).minutes == 5
