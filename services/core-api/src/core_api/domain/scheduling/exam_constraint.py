"""Exam constraint: post-processing on FSRS output (ADR-0009, US-06 AC3).

FSRS knows nothing about exams. Two rules sit on top of it:

1. Nothing is due after the exam.
2. Every learned unit is due at least once in the `EXAM_WINDOW_DAYS` learning days before it.

Both reduce to one cap: a due date may be no later than the learning day before the exam. A unit
whose FSRS due date falls after the window is pulled to that day, which is inside the window. A
unit due before the window comes up before it, and its next due date passes through here again
when it is reviewed. If it is not reviewed, it stays overdue, so it is still due in the window.

The cap gives way in one case: when the exam is tomorrow, the day before the exam is the day of
the review, and a unit must never be due again on the day it was reviewed. The cap is then the
exam day itself, which still satisfies rule 1.

Once the exam day has come (or passed), FSRS output is returned unchanged.

Only `due` changes. Stability and difficulty stay as FSRS computed them, so the next review
starts from the real memory model. A moved exam needs memory_state rebuilt from review_log
(T2.6), because a capped due date does not move back out on its own.
"""

from dataclasses import replace
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import day_bounds, learning_day
from core_api.domain.scheduling.fsrs_adapter import MemoryState

EXAM_WINDOW_DAYS = 14
_ONE_DAY = timedelta(days=1)


def apply_exam_constraint(
    state: MemoryState, exam_day: date, tz: ZoneInfo, day_start_hour: int
) -> MemoryState:
    """Return `state` with `due` capped for the exam on `exam_day` (a learning day)."""
    review_day = learning_day(state.last_review, tz, day_start_hour)
    if exam_day <= review_day:
        return state
    latest = max(exam_day - _ONE_DAY, review_day + _ONE_DAY)
    latest_start, latest_end = day_bounds(latest, tz, day_start_hour)
    if state.due < latest_end:
        return state
    return replace(state, due=latest_start)
