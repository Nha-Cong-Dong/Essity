"""T9.4a (US-10): per-subject statistics, pure. US-10 AC1 numbers, AC4 grid, AC5 work, AC6.
No streak (principle 4). Tests cite their AC code; the rest cite their rule source."""

import dataclasses
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from core_api.domain import stats
from core_api.domain.stats import (
    ActivityEvent,
    BankQuestion,
    Leaf,
    SubjectSpan,
    TypeCounts,
    activity_grid,
    days_left,
    level_for,
    question_bank,
    retention,
    syllabus_progress,
)

UTC_TZ = ZoneInfo("UTC")
SUBJECT = uuid.uuid4()
OTHER = uuid.uuid4()


def at(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def span(created: date, exam: date | None = None, subject: uuid.UUID = SUBJECT) -> SubjectSpan:
    return SubjectSpan(subject, at(created), exam)


def test_days_left_cases():  # US-10 AC1
    today = date(2026, 11, 1)
    assert days_left(date(2026, 11, 11), today) == 10
    assert days_left(today, today) == 0
    assert days_left(date(2026, 10, 30), today) == -2
    assert days_left(None, today) is None


def test_syllabus_percent_weight_and_unit():  # US-10 AC1
    p = syllabus_progress(
        [Leaf(10, "trang", True), Leaf(30, "trang", False), Leaf(20, "trang", True, excluded=True)]
    )
    assert (p.leaves, p.studied_leaves, p.percent) == (2, 1, 50)
    assert (p.studied_weight, p.total_weight, p.unit) == (10, 40, "trang")


def test_syllabus_empty_and_all_excluded():  # US-10 AC1 (empty and all-excluded edge)
    for leaves in ([], [Leaf(5, "trang", True, excluded=True)]):
        p = syllabus_progress(leaves)
        assert (p.leaves, p.percent, p.total_weight, p.unit) == (0, None, 0, None)


def test_question_bank_counts_per_type():  # US-10 AC1
    bank = question_bank(
        [
            BankQuestion("mcq", True, True, 0.95, "correct"),
            BankQuestion("mcq", True, True, 0.95, "incorrect"),  # last wrong: not learned
            BankQuestion("mcq", True, False),
            BankQuestion("essay", False, False),
            BankQuestion("essay", True, True, 0.5, "correct"),  # recall too low
        ]
    )
    assert bank == {"essay": TypeCounts(1, 1, 0), "mcq": TypeCounts(3, 2, 1)}
    assert question_bank([]) == {}


def test_retention_share():  # US-10 AC1 (retention, recall >= 0.9)
    assert retention([]) is None
    assert retention([0.95, 0.9, 0.89, 0.2]) == 0.5


def test_bucket_thresholds():  # US-10 AC4
    assert [level_for(n) for n in (0, 1, 3, 4, 9, 10, 19, 20, 500)] == [0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_grid_layout_across_month_and_year_boundary():  # US-10 AC4 (week/weekday layout)
    start = date(2026, 12, 28)  # Monday
    cells = activity_grid([span(start, date(2027, 1, 5))], [], date(2026, 12, 30), UTC_TZ, 4)
    assert len(cells) == 9
    assert (cells[0].column, cells[0].row) == (0, 0)
    sun = cells[6]
    assert (sun.day, sun.column, sun.row) == (date(2027, 1, 3), 0, 6)
    nxt = cells[7]
    assert (nxt.day, nxt.column, nxt.row) == (date(2027, 1, 4), 1, 0)


def test_grid_starts_mid_week_in_first_column():  # US-10 AC4 (columns = weeks, rows = weekdays)
    cells = activity_grid([span(date(2026, 10, 29))], [], date(2026, 11, 3), UTC_TZ, 4)
    assert (cells[0].column, cells[0].row) == (0, 3)  # Thursday
    assert (cells[4].day, cells[4].column, cells[4].row) == (date(2026, 11, 2), 1, 0)


def test_grid_future_empty_and_exam_marker():  # US-10 AC6
    today = date(2026, 11, 2)
    events = [ActivityEvent(at(today), SUBJECT, cards_saved=30)]
    cells = activity_grid([span(date(2026, 11, 1), date(2026, 11, 5))], events, today, UTC_TZ, 4)
    assert [c.level for c in cells] == [0, 4, 0, 0, 0]
    assert [c.future for c in cells] == [False, False, True, True, True]
    assert [c.exam_day for c in cells] == [False] * 4 + [True]


def test_grid_without_exam_runs_to_today_no_marker():  # US-10 AC4 + DESIGN 6.13 (no exam date)
    cells = activity_grid([span(date(2026, 11, 1))], [], date(2026, 11, 3), UTC_TZ, 4)
    assert len(cells) == 3 and not any(c.exam_day or c.future for c in cells)


def test_grid_exam_passed_still_reaches_exam_day():  # US-10 AC4 (exam passed)
    cells = activity_grid(
        [span(date(2026, 11, 1), date(2026, 11, 3))], [], date(2026, 11, 20), UTC_TZ, 4
    )
    assert cells[-1].day == date(2026, 11, 20)  # today is later than the exam


def test_work_is_cards_plus_answers_with_detail():  # US-10 AC5
    day = date(2026, 11, 2)
    sec_a, sec_b = uuid.uuid4(), uuid.uuid4()
    events = [
        ActivityEvent(at(day, 9), SUBJECT, sec_a, cards_saved=2),
        ActivityEvent(at(day, 10), SUBJECT, sec_b, cards_saved=1),
        ActivityEvent(at(day, 11), SUBJECT, questions_answered=3),
    ]
    (cell,) = activity_grid([span(day)], events, day, UTC_TZ, 4)
    assert (cell.cards_saved, cell.questions_answered, cell.work, cell.level) == (3, 3, 6, 2)
    assert cell.subjects == (SUBJECT,)
    assert set(cell.sections) == {sec_a, sec_b}


def test_day_start_hour_boundary():  # ADR-0009 learning day (US-10 AC5 days)
    day = date(2026, 11, 2)
    events = [
        ActivityEvent(datetime(2026, 11, 3, 3, 59, tzinfo=UTC), SUBJECT, questions_answered=1),
        ActivityEvent(datetime(2026, 11, 3, 4, 0, tzinfo=UTC), SUBJECT, questions_answered=5),
    ]
    cells = activity_grid([span(day)], events, date(2026, 11, 3), UTC_TZ, 4)
    assert [c.questions_answered for c in cells] == [1, 5]


def test_filter_by_subject_and_all():  # US-10 AC4 (filter by subject or all)
    day = date(2026, 11, 2)
    events = [
        ActivityEvent(at(day), SUBJECT, cards_saved=1),
        ActivityEvent(at(day), OTHER, cards_saved=2),
    ]
    spans = [span(day), span(date(2026, 11, 1), subject=OTHER)]
    both = activity_grid(spans, events, day, UTC_TZ, 4)
    assert both[0].day == date(2026, 11, 1) and both[1].cards_saved == 3
    only = activity_grid(spans, events, day, UTC_TZ, 4, subject_id=SUBJECT)
    assert len(only) == 1 and only[0].cards_saved == 1 and only[0].subjects == (SUBJECT,)
    assert activity_grid(spans, events, day, UTC_TZ, 4, subject_id=uuid.uuid4()) == []


def test_activity_before_creation_extends_start():  # US-10 AC4 (first activity before creation)
    day = date(2026, 11, 2)
    events = [ActivityEvent(at(day - timedelta(days=2)), SUBJECT, cards_saved=1)]
    cells = activity_grid([span(day)], events, day, UTC_TZ, 4)
    assert cells[0].day == day - timedelta(days=2)


def test_empty_subject():  # US-10 AC4/AC6 (empty day is a blank cell)
    day = date(2026, 11, 2)
    (cell,) = activity_grid([span(day)], [], day, UTC_TZ, 4)
    assert cell.level == 0 and cell.subjects == () and cell.work == 0


def test_no_streak_anywhere():  # US-10 AC6, principle 4 (no streak)
    names = [n.lower() for n in dir(stats)]
    for cls in (stats.GridCell, stats.SyllabusProgress, stats.TypeCounts, stats.ActivityEvent):
        names += [f.name.lower() for f in dataclasses.fields(cls)]
    assert not [n for n in names if "streak" in n or "chuoi" in n]


@given(
    created=st.dates(date(2026, 1, 1), date(2027, 12, 31)),
    length=st.integers(0, 400),
    counts=st.lists(st.integers(0, 50), max_size=10),
)
def test_grid_size_and_intensity_property(
    created: date, length: int, counts: list[int]
):  # US-10 AC4/AC5 (property)
    exam = created + timedelta(days=length)
    events = [
        ActivityEvent(at(created + timedelta(days=i % (length + 1))), SUBJECT, cards_saved=n)
        for i, n in enumerate(counts)
    ]
    cells = activity_grid([span(created, exam)], events, created, UTC_TZ, 4)
    assert len(cells) == length + 1
    assert all(0 <= c.level <= 4 and c.cards_saved >= 0 for c in cells)
    assert all(0 <= c.row <= 6 for c in cells)
