"""Rules of a document's outline tree (T7.4, US-13, v2 §5 and §7). Pure: no database.

A section has a range in the document's `unit` (page, slide or estimated page), 1-based and
inclusive, and a `weight` (units under it). Progress counts the leaves that are not excluded
(a section is excluded when it or an ancestor is), by weight. A leaf's `studied_weight` is how
much of it the learner has covered, so a partly covered section counts partly (US-13 AC6).
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

RangeCode = Literal["invalid_range", "outside_document", "outside_parent", "children_outside"]


class RangeError(ValueError):
    """The range breaks a rule; `code` is stable and safe to return."""

    def __init__(self, code: RangeCode) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SectionRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    first_page: int
    last_page: int
    weight: float
    studied_weight: float
    excluded: bool


def check_range(
    start: int,
    end: int,
    total: int,
    *,
    parent: tuple[int, int] | None,
    children: Sequence[tuple[int, int]],
) -> None:
    """`0 < start <= end <= total`; inside the parent's range; around every child's range.
    Siblings may touch, overlap or leave gaps: chapters often share a page, and a gap is a part
    the learner leaves out (decision, T7.4)."""
    if not 0 < start <= end:
        raise RangeError("invalid_range")
    if end > total:
        raise RangeError("outside_document")
    if parent is not None and not (parent[0] <= start and end <= parent[1]):
        raise RangeError("outside_parent")
    if any(c_start < start or c_end > end for c_start, c_end in children):
        raise RangeError("children_outside")


def children_of(rows: Sequence[SectionRow]) -> dict[uuid.UUID | None, list[SectionRow]]:
    by_parent: dict[uuid.UUID | None, list[SectionRow]] = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)
    return by_parent


def subtree_ids(rows: Sequence[SectionRow], root: uuid.UUID) -> list[uuid.UUID]:
    """`root` and every section under it."""
    by_parent = children_of(rows)
    found: list[uuid.UUID] = []
    pending = [root]
    while pending:
        current = pending.pop()
        found.append(current)
        pending.extend(c.id for c in by_parent.get(current, []))
    return found


def ancestors(rows: Sequence[SectionRow], section_id: uuid.UUID) -> list[uuid.UUID]:
    """Parent first, up to the root."""
    parents = {row.id: row.parent_id for row in rows}
    chain: list[uuid.UUID] = []
    current = parents.get(section_id)
    while current is not None and current not in chain:
        chain.append(current)
        current = parents.get(current)
    return chain


def excluded_ids(rows: Sequence[SectionRow]) -> set[uuid.UUID]:
    """Sections left out of the count: excluded themselves or under an excluded one."""
    by_parent = children_of(rows)
    out: set[uuid.UUID] = set()

    def walk(row: SectionRow, inherited: bool) -> None:
        gone = inherited or row.excluded
        if gone:
            out.add(row.id)
        for child in by_parent.get(row.id, []):
            walk(child, gone)

    for root in by_parent.get(None, []):
        walk(root, False)
    return out


def leaves(rows: Sequence[SectionRow]) -> list[SectionRow]:
    parents = {row.parent_id for row in rows}
    return [row for row in rows if row.id not in parents]


def covered(row: SectionRow) -> float:
    """Part of a leaf the learner covered, clamped to its weight."""
    return min(max(row.studied_weight, 0.0), row.weight)


def progress(rows: Sequence[SectionRow]) -> float:
    """Share of the weight of the leaves not excluded that is covered (0 when there is none)."""
    gone = excluded_ids(rows)
    counted = [row for row in leaves(rows) if row.id not in gone]
    total = sum(row.weight for row in counted)
    if total <= 0:
        return 0.0
    return sum(covered(row) for row in counted) / total


def section_progress(rows: Sequence[SectionRow]) -> dict[uuid.UUID, float]:
    """Per section: the covered share of the weight of the leaves under it that are not excluded.
    An excluded section reports what it holds, so the learner still sees it."""
    gone = excluded_ids(rows)
    by_id = {row.id: row for row in rows}
    leaf_ids = {row.id for row in leaves(rows)}
    result: dict[uuid.UUID, float] = {}
    for row in rows:
        under = [by_id[i] for i in subtree_ids(rows, row.id) if i in leaf_ids]
        if row.id not in gone:
            under = [leaf for leaf in under if leaf.id not in gone]
        weight = sum(leaf.weight for leaf in under)
        result[row.id] = sum(covered(leaf) for leaf in under) / weight if weight > 0 else 0.0
    return result


def reweigh(
    rows: Sequence[SectionRow], ranges: Mapping[uuid.UUID, tuple[int, int]]
) -> dict[uuid.UUID, float]:
    """New weights after ranges changed: a leaf weighs the units of its range, a parent the sum
    of its children."""
    by_parent = children_of(rows)
    weights: dict[uuid.UUID, float] = {}

    def weigh(row: SectionRow) -> float:
        kids = by_parent.get(row.id, [])
        if kids:
            value = sum(weigh(kid) for kid in kids)
        else:
            start, end = ranges.get(row.id, (row.first_page, row.last_page))
            value = float(end - start + 1)
        weights[row.id] = value
        return value

    for root in by_parent.get(None, []):
        weigh(root)
    return weights
