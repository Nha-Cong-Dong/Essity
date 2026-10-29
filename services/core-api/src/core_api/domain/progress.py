"""Progress numbers (US-10, T5.5a). Pure: no database. Nothing here compares grades or effort
between weeks or subjects (no pressure metrics, US-11 dropped).

- Page coverage: the union of the session ranges over the pages of the subject's indexed
  documents; no exam scope (PRD Q17).
- "Vững": recall >= `SOLID_RECALL`. "Sẵn sàng" is **Q1 tạm** (PRD §8.1): every unit that is not
  skipped has been asked at least once, and at least `READY_SHARE` of them are solid. Pages need
  not be 100%. The "70% right at apply level" condition joins at M5 (US-04b).
- Hours per week come from `review_session`, by learning day, weeks starting on Monday.
"""

import csv
import io
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

SOLID_RECALL = 0.9
READY_SHARE = 0.85
CSV_HEADER = ("section", "subject", "period", "key", "value")


def covered_pages(
    ranges: Iterable[tuple[uuid.UUID, int, int]], page_counts: Mapping[uuid.UUID, int]
) -> int:
    """Distinct file pages covered: ranges are cut to the document's page count, those of a
    document not in `page_counts` are left out."""
    by_document: dict[uuid.UUID, list[tuple[int, int]]] = defaultdict(list)
    for document_id, first, last in ranges:
        total = page_counts.get(document_id)
        if total is None:
            continue
        first, last = max(first, 1), min(last, total)
        if first <= last:
            by_document[document_id].append((first, last))
    covered = 0
    for spans in by_document.values():
        current_end = 0
        for first, last in sorted(spans):
            first = max(first, current_end + 1)
            if last >= first:
                covered += last - first + 1
                current_end = last
    return covered


@dataclass(frozen=True)
class UnitProgress:
    """One active, not skipped unit: `asked` once it has a core schedule, with its recall now."""

    asked: bool
    recall: float | None


@dataclass(frozen=True)
class Readiness:
    units: int
    asked: int
    solid: int
    skipped: int
    ready: bool  # Q1 tạm

    @property
    def solid_percent(self) -> int | None:
        return None if self.units == 0 else round(100 * self.solid / self.units)


def readiness(units: Sequence[UnitProgress], skipped: int = 0) -> Readiness:
    asked = sum(1 for unit in units if unit.asked)
    solid = sum(1 for unit in units if unit.recall is not None and unit.recall >= SOLID_RECALL)
    total = len(units)
    ready = total > 0 and asked == total and solid >= READY_SHARE * total
    return Readiness(units=total, asked=asked, solid=solid, skipped=skipped, ready=ready)


@dataclass(frozen=True)
class SubjectProgress:
    subject_id: uuid.UUID
    name: str
    exam_date: date | None
    pages_covered: int
    pages_total: int
    readiness: Readiness
    days_to_exam: int | None  # exam day minus today; none without an exam


@dataclass(frozen=True)
class StudyWeek:
    week_start: date  # the Monday
    hours: float


def study_weeks(
    sessions: Iterable[tuple[date, datetime, datetime | None]],
) -> list[StudyWeek]:
    """(learning day, started, ended) per sitting -> weeks with any sitting, oldest first. A sitting
    still open adds no hours but its week still counts as studied."""
    seconds: dict[date, float] = defaultdict(float)
    for learning_day, started_at, ended_at in sessions:
        monday = learning_day - timedelta(days=learning_day.weekday())
        seconds[monday] += 0.0 if ended_at is None else (ended_at - started_at).total_seconds()
    return [StudyWeek(monday, seconds[monday] / 3600) for monday in sorted(seconds)]


@dataclass(frozen=True)
class CsvRow:
    section: str
    subject: str
    period: str
    key: str
    value: str


def _safe(cell: str) -> str:
    """A text cell that a spreadsheet could read as a formula gets a leading quote; numbers
    ("-5") are left alone."""
    if cell[:1] in ("=", "+", "-", "@", "\t", "\r"):
        try:
            float(cell)
        except ValueError:
            return "'" + cell
    return cell


def csv_text(rows: Iterable[CsvRow]) -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(
            [
                _safe(row.section),
                _safe(row.subject),
                row.period,
                _safe(row.key),
                _safe(row.value, True),
            ]
        )
    return out.getvalue()
