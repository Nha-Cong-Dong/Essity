"""E2: daily quota of leaf units from remaining units and days to the exam. Pure."""

import uuid
from dataclasses import dataclass, field

import pytest

from core_api.domain.plan import daily_quota, remaining_chapters, todays_units


@dataclass(frozen=True)
class L:
    open: bool = True
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@pytest.mark.parametrize(
    ("remaining", "days", "expected"),
    [(10, 3, 3), (7, 2, 3), (4, 1, 4), (4, 0, 4), (20, 3, 6), (0, 5, 0), (3, 10, 0), (1, 1, 1)],
)
def test_quota_spreads_units_over_days(remaining: int, days: int, expected: int) -> None:
    assert daily_quota(remaining, days) == expected


def test_a_subject_never_studied_starts_with_one_unit() -> None:
    assert daily_quota(3, 10, can_rest=False) == 1


def test_no_exam_date_gives_a_small_steady_amount() -> None:
    assert daily_quota(10, None) == 3 and daily_quota(2, None) == 2


def test_whole_plan_finishes_by_the_exam() -> None:
    remaining = 17
    for days in range(10, 0, -1):
        remaining -= daily_quota(remaining, days)
    assert remaining == 0


def test_todays_units_in_order_and_count_toward_quota() -> None:
    leaves = [L() for _ in range(6)]
    assert todays_units(leaves, 3, 0) == leaves[:2]
    assert todays_units(leaves, 3, 1) == leaves[:1]  # 7 at start, quota 3, one learned
    assert todays_units(leaves, 3, 2) == []  # 8 at start, quota 2, both learned


def test_closed_leaves_are_skipped_and_ahead_gives_nothing() -> None:
    done, a = L(open=False), L()
    assert todays_units([done, a], 5, 0) == []
    assert todays_units([done, a], 5, 0, can_rest=False) == [a]


def test_remaining_chapters_counts_distinct() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert remaining_chapters([a, a, b]) == 2
