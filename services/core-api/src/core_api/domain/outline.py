"""Rules of a document's outline tree (T7.4, US-13, v2 §5 and §7). Pure: no database.

A section has a range in the document's `unit` (page, slide or estimated page), 1-based and
inclusive, and a `weight` (units under it). Progress counts the leaves that are not excluded
(a section is excluded when it or an ancestor is), by weight. A leaf's `studied_weight` is how
much of it the learner has covered, so a partly covered section counts partly (US-13 AC6).
"""

import re
import unicodedata
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


def clamp_studied(studied: float, weight: float) -> float:
    """`studied_weight` kept inside `0 <= studied <= weight` (the column refuses negatives and
    infinity; the weight is the most a section can have covered). NaN counts as nothing."""
    if studied != studied:  # NaN
        return 0.0
    return min(max(studied, 0.0), weight)


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


_NUMBER = re.compile(
    r"^\s*((?:chương|chuong|phần|phan|bài|bai)\s+\d+|\d+(?:\.\d+)*)\s*[.:)\-–]?\s*", re.I
)


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", stripped).split())


def title_key(title: str) -> tuple[str, str]:
    """(number, words) of a section title: "3.4. Ý nghĩa" -> ("3.4", "y nghia"). The number is
    "" for a title without one; the words ignore case, accents and punctuation."""
    found = _NUMBER.match(title)
    if found is None:
        return "", _plain(title)
    number = found.group(1)
    number = _plain(number).replace(" ", "") if number[0].isalpha() else number
    return number, _plain(title[found.end() :])


def _match_siblings(old: Sequence[str], new: Sequence[str]) -> dict[int, int]:
    """Which old sibling each new sibling is: {new position: old position}. Each old one is used
    once. Pass 1 takes number and words equal; pass 2, a number that is unique on both
    sides (a title the reader fixed: ")" became "N(a,σ2)"); pass 3, equal words without a
    number. A number held twice on a side is ambiguous: only pass 1 can match it."""
    old_keys = [title_key(t) for t in old]
    new_keys = [title_key(t) for t in new]
    matched: dict[int, int] = {}
    used: set[int] = set()

    def take(pairs: Sequence[tuple[int, int]]) -> None:
        for n, o in pairs:
            if n not in matched and o not in used:
                matched[n] = o
                used.add(o)

    first_old: dict[tuple[str, str], int] = {}
    for o, key in enumerate(old_keys):
        first_old.setdefault(key, o)
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[int, int]] = []
    for n, key in enumerate(new_keys):
        if key in first_old and key not in seen:
            seen.add(key)
            pairs.append((n, first_old[key]))
    take(pairs)
    # Duplicated keys on the new side: later ones pair with later old duplicates, in order.
    for key in {k for k in new_keys if new_keys.count(k) > 1}:
        news = [n for n, k in enumerate(new_keys) if k == key]
        olds = [o for o, k in enumerate(old_keys) if k == key]
        take(list(zip(news, olds, strict=False)))

    def free(keys: Sequence[tuple[str, str]], skip: set[int]) -> dict[str, list[int]]:
        by_number: dict[str, list[int]] = {}
        for i, (number, _) in enumerate(keys):
            if number and i not in skip:
                by_number.setdefault(number, []).append(i)
        return by_number

    new_free = free(new_keys, set(matched))
    old_free = free(old_keys, used)
    all_new = free(new_keys, set())
    all_old = free(old_keys, set())
    take(
        [
            (ns[0], old_free[number][0])
            for number, ns in new_free.items()
            if len(ns) == 1
            and len(all_new[number]) == 1
            and len(old_free.get(number, [])) == 1
            and len(all_old[number]) == 1
        ]
    )
    by_words: dict[str, int] = {}
    for o, (number, words) in enumerate(old_keys):
        if not number and o not in used and words:
            by_words.setdefault(words, o)
    take(
        [(n, by_words[w]) for n, (number, w) in enumerate(new_keys) if not number and w in by_words]
    )
    return matched


def match_titles(
    old: Sequence[str],
    new: Sequence[str],
    old_parent: Sequence[int | None],
    new_parent: Sequence[int | None],
) -> dict[int, int]:
    """Which old section each new one is, top down: {new index: old index}. `*_parent` is the
    index of each section's parent in its own list (None for a root; parents come first in
    `new`). A section only matches an old one under the old section its parent matched (roots
    only among roots), so a number reused in another chapter never moves a section there; a new
    section with no matched parent matches nothing. Within one parent, `_match_siblings`."""
    matched: dict[int, int] = {}
    groups: dict[int | None, list[int]] = {}
    for n, parent in enumerate(new_parent):
        groups.setdefault(parent, []).append(n)
    old_groups: dict[int | None, list[int]] = {}
    for o, parent in enumerate(old_parent):
        old_groups.setdefault(parent, []).append(o)
    for parent in [None, *range(len(new))]:  # a parent is settled before its children
        news = groups.get(parent, [])
        if not news:
            continue
        if parent is None:
            olds = old_groups.get(None, [])
        elif parent in matched:
            olds = old_groups.get(matched[parent], [])
        else:
            continue
        found = _match_siblings([old[o] for o in olds], [new[n] for n in news])
        matched.update({news[n]: olds[o] for n, o in found.items()})
    return matched
