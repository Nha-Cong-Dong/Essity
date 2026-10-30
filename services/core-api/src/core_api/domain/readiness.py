"""Question readiness (T8.2a, US-14 AC3/AC4/AC6). Pure: no database, no I/O, no LLM.

A question is ready when every section it is linked to is studied and has at least one canonical
card; reviewing the card correctly is not required (AC4).

Small choices the docs leave open (recorded in the T8.2a decisions):
- A linked section marked excluded ("không thi") is ignored. A question whose linked sections are
  all excluded counts as `Unlinked`: it has nothing left to wait for, but must not reach practice
  as if it were ready, so the learner is pointed at re-linking it.
- "Studied" is the section's boolean flag; a partly studied section is not studied.
- A link to a section id that is not in the subject's outline is ignored like an excluded one.
- Waiting sections are listed in natural order of their number ("3.4" before "3.10").
"""

import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    id: uuid.UUID
    label: str  # outline number shown to the learner, e.g. "3.4"
    studied: bool
    excluded: bool = False


@dataclass(frozen=True)
class Card:
    section_id: uuid.UUID
    canonical: bool


@dataclass(frozen=True)
class Ready:
    pass


@dataclass(frozen=True)
class Waiting:
    sections: tuple[Section, ...]  # in natural order of label, never empty


@dataclass(frozen=True)
class Unlinked:
    pass


Readiness = Ready | Waiting | Unlinked

UNLINKED_LINE = "Chưa gắn mục. Sửa bằng thanh lệnh."
READY_LINE = "Sẵn sàng"


def _natural_key(label: str) -> list[tuple[int, int, str]]:
    parts = re.split(r"(\d+)", label.strip())
    return [(0, int(p), "") if p.isdigit() else (1, 0, p.casefold()) for p in parts if p]


def readiness(
    linked_section_ids: Iterable[uuid.UUID],
    sections: Mapping[uuid.UUID, Section],
    cards: Iterable[Card],
) -> Readiness:
    counted = {
        sections[i] for i in set(linked_section_ids) if i in sections and not sections[i].excluded
    }
    if not counted:
        return Unlinked()
    with_canonical = {c.section_id for c in cards if c.canonical}
    waiting = [s for s in counted if not (s.studied and s.id in with_canonical)]
    if not waiting:
        return Ready()
    return Waiting(tuple(sorted(waiting, key=lambda s: _natural_key(s.label))))


def display_line(state: Readiness) -> str:
    """The one neutral line the list shows for a question (AC3, AC4, AC6)."""
    match state:
        case Ready():
            return READY_LINE
        case Waiting(sections=waiting):
            return "Chờ học: mục " + ", ".join(s.label for s in waiting)
        case Unlinked():
            return UNLINKED_LINE


def became_ready(
    linked_section_ids: Sequence[uuid.UUID],
    sections: Mapping[uuid.UUID, Section],
    cards_before: Sequence[Card],
    saved: Card,
) -> bool:
    """True when saving `saved` is what flips the question from not ready to ready (AC4)."""
    before = readiness(linked_section_ids, sections, cards_before)
    after = readiness(linked_section_ids, sections, [*cards_before, saved])
    return not isinstance(before, Ready) and isinstance(after, Ready)
