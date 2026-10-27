"""T2.23 tester: the edges of the places kept for new questions (`_kept_for_new`, plan b2/O1), the
replacement's `exclude` on due units, and the backlog counting units never asked (US-06 AC6,
US-03 AC5, AC8). Each test kills a mutation the earlier tests let live (tester.detail.md)."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import day_bounds
from core_api.domain.scheduling.fsrs_adapter import MemoryState, Phase
from core_api.domain.today import DueUnit, NewQuestion, TodayPlan, compose_today

HCM = ZoneInfo("Asia/Ho_Chi_Minh")
DAY_START = 4
TODAY = date(2026, 11, 2)
NOW = datetime.combine(TODAY, time(20), tzinfo=HCM).astimezone(UTC)


def state(stability: float, last_days_ago: int) -> MemoryState:
    return MemoryState(
        phase=Phase.REVIEW,
        step=None,
        stability=stability,
        difficulty=5.0,
        due=day_bounds(TODAY, HCM, DAY_START)[0] - timedelta(days=1),
        last_review=NOW - timedelta(days=last_days_ago),
    )


def due(subject: uuid.UUID, stability: float = 10.0, last_days_ago: int = 10) -> DueUnit:
    return DueUnit(uuid.uuid4(), subject, uuid.uuid4(), state(stability, last_days_ago))


def new(subject: uuid.UUID, minutes_ago: int) -> NewQuestion:
    return NewQuestion(uuid.uuid4(), subject, NOW - timedelta(minutes=minutes_ago))


def plan(
    units: list[DueUnit],
    fresh: list[NewQuestion],
    exams: dict[uuid.UUID, date],
    unasked: dict[uuid.UUID, int] | None = None,
    **kwargs: object,
) -> TodayPlan:
    return compose_today(
        units,
        fresh,
        exams,
        now=NOW,
        tz=HCM,
        day_start_hour=DAY_START,
        unasked=unasked,
        **kwargs,  # type: ignore[arg-type]
    )


def new_of(result: TodayPlan, subject: uuid.UUID) -> int:
    return sum(i.kind == "new" and i.subject_id == subject for i in result.items)


# US-03 AC8, câu bù. Red when: the replacement takes a due question already in the session (the
# riskiest one here), which the append would put in the session twice.
def test_t223_a_replacement_never_takes_a_due_question_already_in_the_session() -> None:
    subject = uuid.uuid4()
    inside = due(subject, stability=1.0, last_days_ago=30)  # the riskiest
    other = due(subject, stability=100.0, last_days_ago=1)
    result = plan([inside, other], [], {}, exclude=frozenset({inside.question_id}), room=1)
    assert [i.question_id for i in result.items] == [other.question_id]


# Plan b2 (D6): NEW_FLOOR = 5. Red when: the floor changes (the existing test reads the constant
# back, so it cannot see it move).
def test_t223_the_floor_for_new_questions_is_five() -> None:
    mine = uuid.uuid4()
    units = [due(mine) for _ in range(40)]
    result = plan(units, [new(mine, n) for n in range(9)], {})
    assert len(result.items) == 20 and new_of(result, mine) == 5


# Plan O1 "ngày_còn = 0 -> chia cho 1". Red when: a subject examined today gets no quota (its 8
# units never asked fall back to the floor of 5), or a past exam still gets one.
def test_t223_an_exam_today_keeps_its_quota_and_a_past_exam_has_none() -> None:
    today_exam, past_exam, busy = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    units = [due(busy) for _ in range(40)]
    exams = {today_exam: TODAY, past_exam: TODAY - timedelta(days=1)}
    result = plan(units, [new(today_exam, n) for n in range(8)], exams, {today_exam: 8})
    assert new_of(result, today_exam) == 8
    result = plan(units, [new(past_exam, n) for n in range(8)], exams, {past_exam: 8})
    assert new_of(result, past_exam) == 5  # the floor only


# Plan O1 "môn thi gần trước". Red when: when the quotas pass the day's cap, the farther exam is
# served first and the nearer one loses places (A: ceil(15 / 1) = 15, B: ceil(100 / 10) = 10).
def test_t223_the_nearest_exam_takes_its_quota_first_when_quotas_pass_the_cap() -> None:
    near, far = uuid.uuid4(), uuid.uuid4()
    fresh = [new(near, 1000 + n) for n in range(15)] + [new(far, n) for n in range(10)]
    exams = {near: TODAY + timedelta(days=2), far: TODAY + timedelta(days=11)}
    result = plan([], fresh, exams, {near: 15, far: 100})
    assert len(result.items) == 20
    assert new_of(result, near) == 15 and new_of(result, far) == 5


# Plan O1. Red when: an exam subject takes more kept places than its quota (ceil(2 / 2) = 1), so
# the rest of the floor no longer goes to the newest questions of any subject.
def test_t223_a_subject_takes_no_more_than_its_quota_of_kept_places() -> None:
    exam, other = uuid.uuid4(), uuid.uuid4()
    units = [due(other) for _ in range(40)]
    fresh = [new(exam, 1000 + n) for n in range(5)] + [new(other, n) for n in range(5)]
    result = plan(units, fresh, {exam: TODAY + timedelta(days=3)}, {exam: 2})
    assert new_of(result, exam) == 1 and new_of(result, other) == 4


# US-03 AC5 + T2.23 ("backlog tính cả mảnh chưa hỏi"). Red when: units never asked do not count,
# so 50 of them two days before the exam (3 sessions) give no note.
def test_t223_the_backlog_counts_units_never_asked() -> None:
    subject = uuid.uuid4()
    result = plan([], [], {subject: TODAY + timedelta(days=2)}, {subject: 50})
    assert result.backlog is not None
    assert (result.backlog.subject_id, result.backlog.sessions, result.backlog.days) == (
        subject,
        3,
        2,
    )
