"""The study ledger as the suggestions read it (T7.10b, US-15 AC4, AC10). Pure: no database.

One entry per session, learning day and section (T7.8 writes them in the Save transaction). The
ledger says which subject and section the learner studied on a day, hence also which subject was
not studied; it never says a day was missed, and nothing here counts or compares days.
"""

import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core_api.domain.learning_day import learning_day


@dataclass(frozen=True)
class LedgerEntry:
    subject_id: uuid.UUID
    learning_day: date
    section_id: uuid.UUID | None
    units_saved: int


def ledger_day(instant: datetime, tz: ZoneInfo, day_start_hour: int) -> date:
    """The day a Save belongs to: cut at `day_start_hour` local time, not midnight (AC10)."""
    return learning_day(instant, tz, day_start_hour)


def last_studied_days(entries: Iterable[LedgerEntry]) -> dict[uuid.UUID, date]:
    """Most recent learning day of each subject that has an entry: the tie-break of the ranking."""
    last: dict[uuid.UUID, date] = {}
    for e in entries:
        if e.subject_id not in last or e.learning_day > last[e.subject_id]:
            last[e.subject_id] = e.learning_day
    return last


def studied_on(entries: Iterable[LedgerEntry], day: date) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Subject -> sections studied on `day` (a Save with no section counts for its subject)."""
    out: dict[uuid.UUID, set[uuid.UUID]] = {}
    for e in entries:
        if e.learning_day == day:
            sections = out.setdefault(e.subject_id, set())
            if e.section_id is not None:
                sections.add(e.section_id)
    return out


def subjects_not_studied(
    entries: Iterable[LedgerEntry], day: date, subject_ids: Collection[uuid.UUID]
) -> set[uuid.UUID]:
    studied = studied_on(entries, day)
    return {s for s in subject_ids if s not in studied}
