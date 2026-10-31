"""T7.4 (US-13 AC4-AC6): range rules, progress by weight over leaves not excluded."""

import uuid

import pytest

from core_api.domain.outline import (
    RangeError,
    SectionRow,
    check_range,
    excluded_ids,
    progress,
    reweigh,
    section_progress,
)


def row(
    id: uuid.UUID,
    parent: uuid.UUID | None,
    start: int,
    end: int,
    *,
    studied: float = 0,
    excluded: bool = False,
    weight: float | None = None,
) -> SectionRow:
    return SectionRow(
        id,
        parent,
        start,
        end,
        float(end - start + 1) if weight is None else weight,
        studied,
        excluded,
    )


A, A1, A2, B = (uuid.uuid4() for _ in range(4))


def tree(**kw: dict[str, float | bool]) -> list[SectionRow]:
    return [
        row(A, None, 1, 10, **kw.get("A", {})),  # type: ignore[arg-type]
        row(A1, A, 1, 4, **kw.get("A1", {})),  # type: ignore[arg-type]
        row(A2, A, 5, 10, **kw.get("A2", {})),  # type: ignore[arg-type]
        row(B, None, 11, 20, **kw.get("B", {})),  # type: ignore[arg-type]
    ]


@pytest.mark.parametrize(
    ("start", "end", "total", "parent", "children", "code"),
    [
        (0, 3, 10, None, [], "invalid_range"),
        (5, 4, 10, None, [], "invalid_range"),
        (-1, 4, 10, None, [], "invalid_range"),
        (1, 11, 10, None, [], "outside_document"),
        (2, 6, 10, (3, 8), [], "outside_parent"),
        (3, 9, 10, (3, 8), [], "outside_parent"),
        (3, 8, 10, None, [(2, 4)], "children_outside"),
        (3, 8, 10, None, [(5, 9)], "children_outside"),
    ],
)
def test_us13_ac4_range_rules_refuse(
    start: int,
    end: int,
    total: int,
    parent: tuple[int, int] | None,
    children: list[tuple[int, int]],
    code: str,
) -> None:
    with pytest.raises(RangeError) as raised:
        check_range(start, end, total, parent=parent, children=children)
    assert raised.value.code == code


def test_us13_ac4_range_rules_accept_the_edges() -> None:
    check_range(1, 10, 10, parent=None, children=[])
    check_range(3, 8, 10, parent=(3, 8), children=[(3, 8)])
    check_range(3, 3, 10, parent=(1, 10), children=[])
    # touching and overlapping siblings are not checked
    check_range(4, 6, 10, parent=(1, 10), children=[])


def test_us13_ac5_progress_is_by_weight_over_leaves() -> None:
    rows = tree(A1={"studied": 4.0})
    # leaves A1 (4), A2 (6), B (10): 4 / 20
    assert progress(rows) == pytest.approx(0.2)


def test_us13_ac5_excluded_section_is_out_of_progress() -> None:
    rows = tree(A1={"studied": 4.0}, B={"excluded": True})
    assert progress(rows) == pytest.approx(0.4)


def test_us13_ac5_excluding_a_parent_excludes_its_children() -> None:
    rows = tree(A={"excluded": True}, B={"studied": 10.0})
    assert excluded_ids(rows) == {A, A1, A2}
    assert progress(rows) == pytest.approx(1.0)


def test_us13_ac5_nothing_counted_is_zero() -> None:
    assert progress([]) == 0.0
    assert progress(tree(A={"excluded": True}, B={"excluded": True})) == 0.0


def test_us13_ac6_partial_coverage_counts_partly() -> None:
    rows = tree(A2={"studied": 3.0})
    assert progress(rows) == pytest.approx(3 / 20)
    per = section_progress(rows)
    assert per[A2] == pytest.approx(0.5)
    assert per[A] == pytest.approx(3 / 10)
    assert per[A1] == 0.0


def test_us13_ac6_coverage_over_weight_is_clamped() -> None:
    assert progress(tree(B={"studied": 99.0})) == pytest.approx(10 / 20)


def test_section_progress_of_an_excluded_section_shows_what_it_holds() -> None:
    rows = tree(A1={"studied": 4.0}, A={"excluded": True})
    per = section_progress(rows)
    assert per[A] == pytest.approx(0.4)
    assert per[A1] == pytest.approx(1.0)


def test_reweigh_leaf_by_range_parent_by_sum() -> None:
    rows = tree()
    weights = reweigh(rows, {A1: (1, 2)})
    assert weights[A1] == 2
    assert weights[A] == 2 + 6
    assert weights[B] == 10
