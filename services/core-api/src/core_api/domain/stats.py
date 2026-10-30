"""Per-subject statistics (US-10, T9.4a). Pure: no database. Reuses `mastery.is_learned` for
"thuộc" and `learning_day` for days. There is no streak or longest streak anywhere, and nothing
compares weeks or people (principle 4)."""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import learning_day
from core_api.domain.mastery import PracticeVerdict, is_learned
from core_api.domain.progress import SOLID_RECALL

# Cards saved + questions answered in a day -> level 1..4 at these lower bounds; 0 is empty.
LEVEL_FLOORS = (1, 4, 10, 20)


def days_left(exam_date: date | None, today: date) -> int | None:
    """Learning days to the exam: 0 on the day, below 0 once it is over; none without an exam."""
    return None if exam_date is None else (exam_date - today).days


@dataclass(frozen=True)
class Leaf:
    weight: float
    unit: str
    studied: bool
    excluded: bool = False


@dataclass(frozen=True)
class SyllabusProgress:
    leaves: int
    studied_leaves: int
    percent: int | None  # none when no leaf counts
    studied_weight: float
    total_weight: float
    unit: str | None


def syllabus_progress(leaves: Iterable[Leaf]) -> SyllabusProgress:
    """Leaves marked excluded are dropped from both sides."""
    counted = [leaf for leaf in leaves if not leaf.excluded]
    studied = [leaf for leaf in counted if leaf.studied]
    percent = round(100 * len(studied) / len(counted)) if counted else None
    return SyllabusProgress(
        leaves=len(counted),
        studied_leaves=len(studied),
        percent=percent,
        studied_weight=sum(leaf.weight for leaf in studied),
        total_weight=sum(leaf.weight for leaf in counted),
        unit=counted[0].unit if counted else None,
    )


@dataclass(frozen=True)
class BankQuestion:
    question_type: str
    ready: bool  # its sections are studied and have a canonical card (T8.2)
    practiced: bool
    retrievability: float | None = None
    last_verdict: PracticeVerdict | None = None


@dataclass(frozen=True)
class TypeCounts:
    ready: int = 0
    practiced: int = 0
    mastered: int = 0


def question_bank(questions: Iterable[BankQuestion]) -> dict[str, TypeCounts]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for q in questions:
        row = counts[q.question_type]
        row[0] += q.ready
        row[1] += q.practiced
        row[2] += q.retrievability is not None and is_learned(q.retrievability, q.last_verdict)
    return {kind: TypeCounts(*row) for kind, row in sorted(counts.items())}


def retention(retrievabilities: Sequence[float]) -> float | None:
    """Share of canonical cards with recall today >= `SOLID_RECALL`; none without cards."""
    if not retrievabilities:
        return None
    return sum(r >= SOLID_RECALL for r in retrievabilities) / len(retrievabilities)


@dataclass(frozen=True)
class ActivityEvent:
    """One row of the study ledger or answer history."""

    at: datetime
    subject_id: uuid.UUID
    section_id: uuid.UUID | None = None
    cards_saved: int = 0
    questions_answered: int = 0


@dataclass(frozen=True)
class SubjectSpan:
    subject_id: uuid.UUID
    created_at: datetime
    exam_date: date | None


@dataclass(frozen=True)
class GridCell:
    day: date
    column: int  # week, from the Monday of the first week
    row: int  # weekday, Monday 0
    level: int  # 0..4
    future: bool
    exam_day: bool
    subjects: tuple[uuid.UUID, ...]
    sections: tuple[uuid.UUID, ...]
    cards_saved: int
    questions_answered: int

    @property
    def work(self) -> int:
        return self.cards_saved + self.questions_answered


def level_for(work: int) -> int:
    return sum(work >= floor for floor in LEVEL_FLOORS)


def activity_grid(
    spans: Sequence[SubjectSpan],
    events: Iterable[ActivityEvent],
    today: date,
    tz: ZoneInfo,
    day_start_hour: int,
    subject_id: uuid.UUID | None = None,
) -> list[GridCell]:
    """Every learning day from the first subject creation (or first activity, if earlier) to the
    exam date (today when there is none). Days after today are empty. `subject_id` filters."""
    chosen = [s for s in spans if subject_id is None or s.subject_id == subject_id]
    if not chosen:
        return []
    ids = {s.subject_id for s in chosen}
    daily: dict[date, list[ActivityEvent]] = defaultdict(list)
    for event in events:
        if event.subject_id in ids:
            daily[learning_day(event.at, tz, day_start_hour)].append(event)
    start = min(learning_day(s.created_at, tz, day_start_hour) for s in chosen)
    if daily:
        start = min(start, min(daily))
    exams = [s.exam_date for s in chosen if s.exam_date is not None]
    exam_day = max(exams) if exams else None
    end = max([today, *exams]) if exams else today
    end = max(end, start, max(daily, default=start))
    first_monday = start - timedelta(days=start.weekday())
    cells: list[GridCell] = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        rows = daily.get(day, [])
        cards = sum(e.cards_saved for e in rows)
        answered = sum(e.questions_answered for e in rows)
        future = day > today
        cells.append(
            GridCell(
                day=day,
                column=(day - first_monday).days // 7,
                row=day.weekday(),
                level=0 if future else level_for(cards + answered),
                future=future,
                exam_day=day == exam_day,
                subjects=tuple(sorted({e.subject_id for e in rows}, key=str)),
                sections=tuple(
                    sorted({e.section_id for e in rows if e.section_id is not None}, key=str)
                ),
                cards_saved=cards,
                questions_answered=answered,
            )
        )
    return cells


__all__ = [
    "ActivityEvent",
    "BankQuestion",
    "GridCell",
    "Leaf",
    "SubjectSpan",
    "SyllabusProgress",
    "TypeCounts",
    "activity_grid",
    "days_left",
    "level_for",
    "question_bank",
    "retention",
    "syllabus_progress",
]
