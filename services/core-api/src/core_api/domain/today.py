"""Compose today's session (T2.7, ARCH §5.3, US-03 AC3–AC6). Pure: no database, no AI.

Choices for what the spec leaves open (us-03 §9 #2–#5, plan `t2.6-t2.7-replay-today.md`):

- Every question takes `MINUTES_PER_QUESTION`; at MVP every question is "nhận biết" (T5.2 adds
  the ladder), so the 20-question cap and the 30-minute cap meet.
- Risk = probability of recall now, times a weight that falls from 1 to `NEAR_EXAM_WEIGHT` over
  the `EXAM_WINDOW_DAYS` before the exam: a close exam makes its units count as riskier.
- Nobody starves (Q5): each subject with a due unit gets its riskiest one in first; the rest of
  the room goes by risk alone.
- New questions: until documents arrive (M4) a question's creation time stands for "the latest
  document" (us-03 §9 #5), newest first. Places are kept for them so a backlog of due units
  never starves the units not yet asked (T2.23, US-06 AC6): `NEW_FLOOR`, or more when a subject's
  exam is near: ceil(units never asked / learning days left before the exam) for each such
  subject, at most `MAX_QUESTIONS`. Places they do not fill go back to the due units.
- Backlog (AC5): before a subject's exam come the due units of every subject examined that day
  or earlier (one shared session a day, AC7); ceil(units / MAX_QUESTIONS) sessions more than the
  learning days left gives a neutral note. Units are counted, not questions: a question that
  checks several units counts each. The wording ("cần thêm khoảng N phiên") is T2.8's.
"""

import math
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import day_bounds, learning_day
from core_api.domain.scheduling.exam_constraint import EXAM_WINDOW_DAYS
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, MemoryState

MAX_QUESTIONS = 20
MAX_MINUTES = 30
MINUTES_PER_QUESTION = 1.5
NEAR_EXAM_WEIGHT = 0.5
NEW_FLOOR = 5

_SCHEDULER = FsrsScheduler()


@dataclass(frozen=True)
class DueUnit:
    """A (unit, core facet) with its schedule, and the question that asks about it."""

    unit_id: uuid.UUID
    subject_id: uuid.UUID
    question_id: uuid.UUID
    state: MemoryState


@dataclass(frozen=True)
class NewQuestion:
    """A question none of whose units has been reviewed yet."""

    question_id: uuid.UUID
    subject_id: uuid.UUID
    created_at: datetime


@dataclass(frozen=True)
class PlannedQuestion:
    question_id: uuid.UUID
    subject_id: uuid.UUID
    kind: Literal["due", "new"]


@dataclass(frozen=True)
class Backlog:
    """More due units than sessions left before the exam (AC5): `sessions` in `days`."""

    subject_id: uuid.UUID
    sessions: int
    days: int


@dataclass(frozen=True)
class TodayPlan:
    items: list[PlannedQuestion]
    minutes: int
    backlog: Backlog | None
    next_day: date | None  # the next learning day something is due, when nothing is today


def compose_today(
    units: Iterable[DueUnit],
    new_questions: Iterable[NewQuestion],
    exams: Mapping[uuid.UUID, date],
    *,
    now: datetime,
    tz: ZoneInfo,
    day_start_hour: int,
    unasked: Mapping[uuid.UUID, int] | None = None,
    exclude: frozenset[uuid.UUID] = frozenset(),
    room: int | None = None,
) -> TodayPlan:
    """Today's session from every scheduled unit (due or not), the new questions and each
    subject's exam day. `unasked`: units never asked by subject (exam quota, backlog); `exclude`:
    questions already in the session; `room`: places to fill, at most the day's cap (the
    replacement for a skipped question, T2.23)."""
    today = learning_day(now, tz, day_start_hour)
    end_of_today = day_bounds(today, tz, day_start_hour)[1]
    scheduled = list(units)
    never = unasked or {}
    due = [unit for unit in scheduled if unit.state.due < end_of_today]

    def risk(unit: DueUnit) -> float:
        recall = _SCHEDULER.retrievability(unit.state, now)
        return recall * _exam_weight(exams.get(unit.subject_id), today)

    ranked = sorted((u for u in due if u.question_id not in exclude), key=risk)
    first_of_each: dict[uuid.UUID, DueUnit] = {}
    for unit in ranked:
        first_of_each.setdefault(unit.subject_id, unit)
    ordered = [*first_of_each.values(), *(u for u in ranked if u not in first_of_each.values())]

    limit = _room() if room is None else min(room, _room())
    fresh = [q for q in new_questions if q.question_id not in exclude]
    fresh.sort(key=lambda q: q.created_at, reverse=True)
    kept = _kept_for_new(fresh, exams, never, today, min(limit, MAX_QUESTIONS))

    items: list[PlannedQuestion] = []
    asked: set[uuid.UUID] = set()
    for unit in ordered:
        _add(
            items,
            asked,
            PlannedQuestion(unit.question_id, unit.subject_id, "due"),
            limit - len(kept),
        )
    for question in kept:
        _add(items, asked, PlannedQuestion(question.question_id, question.subject_id, "new"), limit)
    for unit in ordered:  # what the kept places did not use goes back to the due units
        _add(items, asked, PlannedQuestion(unit.question_id, unit.subject_id, "due"), limit)
    for question in fresh:
        _add(items, asked, PlannedQuestion(question.question_id, question.subject_id, "new"), limit)

    next_day = None
    if not items and scheduled and room is None:
        next_day = min(learning_day(u.state.due, tz, day_start_hour) for u in scheduled)
    return TodayPlan(
        items=items,
        minutes=math.ceil(len(items) * MINUTES_PER_QUESTION),
        backlog=_backlog(due, exams, today, never),
        next_day=next_day,
    )


def _room() -> int:
    return min(MAX_QUESTIONS, math.floor(MAX_MINUTES / MINUTES_PER_QUESTION))


def _kept_for_new(
    fresh: Sequence[NewQuestion],
    exams: Mapping[uuid.UUID, date],
    unasked: Mapping[uuid.UUID, int],
    today: date,
    limit: int,
) -> list[NewQuestion]:
    """The new questions that hold a place whatever is due. Each subject with an exam still to
    come takes its quota first (the nearest exam first, newest question first inside a subject);
    the rest of the places go to the newest of any subject. Without this, a subject whose exam is
    near but whose questions are older never gets its units asked while another subject's newer
    questions fill the places (review of the T2.23 plan)."""
    quota = {
        subject: math.ceil(count / max(1, (exams[subject] - today).days - 1))
        for subject, count in unasked.items()
        if subject in exams and exams[subject] >= today and count > 0
    }
    places = min(limit, max(NEW_FLOOR, sum(quota.values())), len(fresh))
    kept: list[NewQuestion] = []
    for subject in sorted(quota, key=lambda s: exams[s]):
        mine = [q for q in fresh if q.subject_id == subject][: quota[subject]]
        kept.extend(mine[: places - len(kept)])
    for question in fresh:
        if len(kept) >= places:
            break
        if question not in kept:
            kept.append(question)
    return kept


def _add(
    items: list[PlannedQuestion],
    asked: set[uuid.UUID],
    item: PlannedQuestion,
    limit: int | None = None,
) -> None:
    if item.question_id in asked or len(items) >= (_room() if limit is None else limit):
        return
    asked.add(item.question_id)
    items.append(item)


def _exam_weight(exam_day: date | None, today: date) -> float:
    if exam_day is None or exam_day < today:  # no exam, or it is over
        return 1.0
    days_left = (exam_day - today).days
    closeness = max(0.0, 1 - days_left / EXAM_WINDOW_DAYS)
    return 1 - (1 - NEAR_EXAM_WEIGHT) * closeness


def _backlog(
    due: Sequence[DueUnit],
    exams: Mapping[uuid.UUID, date],
    today: date,
    unasked: Mapping[uuid.UUID, int],
) -> Backlog | None:
    """Every subject shares the one session a day (AC7), so before a subject's exam come the due
    units of every subject examined that day or earlier, and the units never asked count with
    them (T2.23). The worst subject by sessions per day."""
    counts: dict[uuid.UUID, int] = {}
    for unit in due:
        counts[unit.subject_id] = counts.get(unit.subject_id, 0) + 1
    for subject_id, count in unasked.items():
        counts[subject_id] = counts.get(subject_id, 0) + count
    upcoming = {s: exams[s] for s in counts if s in exams and exams[s] > today}
    worst: Backlog | None = None
    for subject_id, exam_day in sorted(upcoming.items(), key=lambda item: item[1]):
        units = sum(counts[s] for s, day in upcoming.items() if day <= exam_day)
        sessions, days = math.ceil(units / MAX_QUESTIONS), (exam_day - today).days
        if sessions > days and (worst is None or sessions / days > worst.sessions / worst.days):
            worst = Backlog(subject_id, sessions, days)
    return worst
