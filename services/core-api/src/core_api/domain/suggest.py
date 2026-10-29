"""Suggest what to study next (T7.10a, v2 design §6.1 and §16.1 Q-A). Pure: no database, no I/O.

Rules (Q-A):

- Next item of a subject = first leaf of the syllabus not yet fully covered (excluded leaves never
  count), unless a "prerequisite" edge points to an uncovered leaf: that one comes first.
  Holes left by studying ahead are therefore suggested on their own. A partly covered leaf is
  suggested for its remaining pages.
- Tightness = remaining weight / max(days left, 1). The top `MAX_SUGGESTIONS` subjects go on
  Today; a tie goes to the subject studied longest ago (never studied = longest).
- Exam passed: not ranked. No exam date: ranked after every dated subject.
- Filters are applied before ranking.
- The pace line holds numbers only, never "phải/cần/kịp/trễ" (no pressure wording).

Small choices the design leaves open: an open prerequisite is followed at any syllabus position
(orchestrator, 30/10); the remaining weight of a mixed-unit syllabus is summed as is and shown in
the unit of the first remaining leaf; `suggest_for_subject` answers even after the exam date.
"""

import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

MAX_SUGGESTIONS = 2

SuggestionKind = Literal["next_leaf", "review_practice", "free_session"]


@dataclass(frozen=True)
class Leaf:
    id: uuid.UUID
    title: str
    weight: float
    unit: str
    excluded: bool = False
    covered_weight: float = 0
    prerequisites: tuple[uuid.UUID, ...] = ()

    @property
    def remaining(self) -> float:
        return max(self.weight - self.covered_weight, 0)

    @property
    def open(self) -> bool:
        return not self.excluded and self.remaining > 0


@dataclass(frozen=True)
class SubjectInput:
    id: uuid.UUID
    exam_date: date | None
    last_studied_day: date | None
    leaves: Sequence[Leaf]  # syllabus order


@dataclass(frozen=True)
class SuggestFilter:
    """`only_subjects`: "this week only subject A". `hidden_until`: "subject B after date"."""

    only_subjects: Collection[uuid.UUID] | None = None
    hidden_until: Mapping[uuid.UUID, date] = field(default_factory=lambda: dict[uuid.UUID, date]())


@dataclass(frozen=True)
class Pace:
    """Numbers only. `days_left` is None without a (future) exam date."""

    remaining_leaves: int
    remaining_weight: float
    unit: str | None
    days_left: int | None

    @property
    def text(self) -> str:
        line = f"còn {self.remaining_leaves} mục"
        if self.unit is not None:
            line += f" ({self.remaining_weight:g} {self.unit})"
        if self.days_left is not None:
            line += f", {self.days_left} ngày"
        return line


@dataclass(frozen=True)
class Suggestion:
    subject_id: uuid.UUID
    kind: SuggestionKind
    leaf_id: uuid.UUID | None
    leaf_title: str | None
    remaining_weight: float | None  # of the suggested leaf (a partly covered leaf: what is left)
    partial: bool
    unit: str | None
    pace: Pace


def _days_left(exam: date | None, today: date) -> int | None:
    if exam is None or exam < today:
        return None
    return (exam - today).days


def next_leaf(leaves: Sequence[Leaf]) -> Leaf | None:
    """First open leaf, replaced by its earliest open prerequisite (followed transitively).

    A prerequisite cycle falls back to plain syllabus order.
    """
    position = {leaf.id: i for i, leaf in enumerate(leaves)}
    open_ids = {leaf.id for leaf in leaves if leaf.open}
    first = next((leaf for leaf in leaves if leaf.open), None)
    current = first
    seen: set[uuid.UUID] = set()
    while current is not None:
        if current.id in seen:
            return first
        seen.add(current.id)
        pending = [p for p in current.prerequisites if p in open_ids]
        if not pending:
            return current
        current = leaves[position[min(pending, key=position.__getitem__)]]
    return None


def _pace(subject: SubjectInput, today: date) -> Pace:
    open_leaves = [leaf for leaf in subject.leaves if leaf.open]
    return Pace(
        remaining_leaves=len(open_leaves),
        remaining_weight=sum(leaf.remaining for leaf in open_leaves),
        unit=open_leaves[0].unit if open_leaves else None,
        days_left=_days_left(subject.exam_date, today),
    )


def suggest_for_subject(subject: SubjectInput, today: date) -> Suggestion:
    """The "Gợi ý cho hôm nay" button: same rules, no ranking, no exam check."""
    pace = _pace(subject, today)
    if not subject.leaves:
        return Suggestion(subject.id, "free_session", None, None, None, False, None, pace)
    leaf = next_leaf(subject.leaves)
    if leaf is None:  # fully studied, or every leaf excluded
        return Suggestion(subject.id, "review_practice", None, None, None, False, None, pace)
    return Suggestion(
        subject.id,
        "next_leaf",
        leaf.id,
        leaf.title,
        leaf.remaining,
        leaf.covered_weight > 0,
        leaf.unit,
        pace,
    )


def _rank_key(subject: SubjectInput, today: date) -> tuple[int, float, date, str]:
    pace = _pace(subject, today)
    last = subject.last_studied_day or date.min
    if pace.days_left is None:  # no exam date: after every dated subject
        return (1, 0.0, last, str(subject.id))
    tightness = pace.remaining_weight / max(pace.days_left, 1)
    return (0, -tightness, last, str(subject.id))


def _eligible(
    subjects: Sequence[SubjectInput], today: date, filters: SuggestFilter | None
) -> list[SubjectInput]:
    flt = filters or SuggestFilter()
    return [
        s
        for s in subjects
        if (flt.only_subjects is None or s.id in flt.only_subjects)
        and not (s.id in flt.hidden_until and today < flt.hidden_until[s.id])
        and not (s.exam_date is not None and s.exam_date < today)
    ]


def suggest_today(
    subjects: Sequence[SubjectInput],
    today: date,
    filters: SuggestFilter | None = None,
) -> list[Suggestion]:
    """At most `MAX_SUGGESTIONS` subjects with something left to study, tightest first."""
    studying = [s for s in _eligible(subjects, today, filters) if _pace(s, today).remaining_leaves]
    ranked = sorted(studying, key=lambda s: _rank_key(s, today))
    return [suggest_for_subject(s, today) for s in ranked[:MAX_SUGGESTIONS]]


def suggest_finished(
    subjects: Sequence[SubjectInput],
    today: date,
    filters: SuggestFilter | None = None,
) -> list[Suggestion]:
    """Eligible subjects with nothing left to study (review_practice / free_session)."""
    done = [s for s in _eligible(subjects, today, filters) if not _pace(s, today).remaining_leaves]
    return [suggest_for_subject(s, today) for s in sorted(done, key=lambda s: _rank_key(s, today))]
