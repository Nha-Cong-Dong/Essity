"""T8.5a: mixing due practice questions into Ôn hôm nay (US-03 AC4, US-06 AC8). Pure."""

import uuid

from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.practice_mix import (
    CARD_SECONDS,
    KIND_FLOOR,
    Kind,
    MixItem,
    PracticeQuestion,
    card_seconds,
    mix,
    practice_seconds,
    split_practice,
)
from core_api.domain.today import MAX_QUESTIONS


def _id(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _card(n: int, risk: float) -> MixItem:
    return MixItem(_id(n), "card", risk, card_seconds())


def _practice(n: int, risk: float, seconds: float = 300.0) -> MixItem:
    return MixItem(_id(n), "practice", risk, seconds)


def test_practice_takes_longer_than_a_card_us03_ac4() -> None:
    assert practice_seconds(30) == CARD_SECONDS  # never below a card
    assert practice_seconds(240) == 240
    assert practice_seconds(240) > card_seconds()


def test_riskiest_first_regardless_of_kind_us03_ac4() -> None:
    plan = mix([_card(1, 0.2), _practice(2, 0.9), _card(3, 0.5)], floor=0)
    assert [i.item_id for i in plan.items] == [_id(2), _id(3), _id(1)]


def test_shared_minutes_cap_us03_ac4() -> None:
    plan = mix([_practice(n, 1 - n / 100, 600) for n in range(1, 6)], floor=0)
    assert len(plan.items) == 3
    assert plan.minutes == 30  # 3 x 10 min


def test_item_too_long_is_skipped_and_next_tried() -> None:
    plan = mix([_practice(1, 0.9, 1000), _practice(2, 0.8, 1000), _card(3, 0.1)], floor=0)
    assert [i.item_id for i in plan.items] == [_id(1), _id(3)]  # 2nd would reach 2000 s
    assert sum(i.seconds for i in plan.items) <= 1800


def test_item_cap_us03_ac4() -> None:
    plan = mix([_card(n, 0.5) for n in range(50)], max_minutes=600)
    assert len(plan.items) == MAX_QUESTIONS


def test_floor_keeps_places_for_both_kinds_us03_ac4() -> None:
    cards = [_card(n, 0.9) for n in range(30)]
    practice = [_practice(100 + n, 0.1, 90) for n in range(5)]
    plan = mix([*cards, *practice])
    got = [i for i in plan.items if i.kind == "practice"]
    assert len(got) == KIND_FLOOR
    assert {i.item_id for i in got} == {i.item_id for i in practice[:KIND_FLOOR]}


def test_no_floor_when_only_one_kind() -> None:
    plan = mix([_card(n, 0.5) for n in range(5)])
    assert len(plan.items) == 5
    assert all(i.kind == "card" for i in plan.items)


def test_empty_and_duplicates() -> None:
    empty = mix([])
    assert empty.items == []
    assert empty.minutes == 0
    assert len(mix([_card(1, 0.5), _card(1, 0.5)]).items) == 1


def test_tie_break_is_deterministic() -> None:
    items = [_practice(2, 0.5, 90), _card(3, 0.5), _card(1, 0.5), _practice(4, 0.5, 90)]
    first = mix(items, floor=0)
    assert [i.item_id for i in first.items] == [_id(1), _id(3), _id(2), _id(4)]
    assert mix(list(reversed(items)), floor=0) == first


def test_split_due_only_in_on_never_attempted_only_in_practice_us06_ac8() -> None:
    qs = [
        PracticeQuestion(_id(1), ready=True),  # never attempted
        PracticeQuestion(_id(2), ready=True, scheduled=True, due=True),
        PracticeQuestion(_id(3), ready=True, scheduled=True, due=False),
        PracticeQuestion(_id(4), ready=False),
        PracticeQuestion(_id(5), ready=True, scheduled=True, due=True, removed=True),
    ]
    due, fresh = split_practice(qs)
    assert due == [_id(2)]
    assert fresh == [_id(1)]
    assert not set(due) & set(fresh)


_KINDS: list[Kind] = ["card", "practice"]


@given(
    st.lists(
        st.tuples(st.sampled_from(_KINDS), st.floats(0, 1), st.floats(90, 300)),
        max_size=60,
    ),
    st.randoms(use_true_random=False),
)
def test_properties_cap_floor_no_dup_stable_us03_ac4(
    raw: list[tuple[Kind, float, float]], rnd: object
) -> None:
    items = [MixItem(_id(n), kind, risk, secs) for n, (kind, risk, secs) in enumerate(raw)]
    plan = mix(items)
    ids = [i.item_id for i in plan.items]
    assert len(ids) == len(set(ids))
    assert len(ids) <= MAX_QUESTIONS
    assert sum(i.seconds for i in plan.items) <= 1800
    assert plan.minutes <= 30
    kinds = {i.kind for i in items}
    for kind in kinds if len(kinds) > 1 else ():  # seconds <= 300: both floors fit the 30 minutes
        have = [i for i in items if i.kind == kind]
        got = [i for i in plan.items if i.kind == kind]
        assert len(got) >= min(KIND_FLOOR, len(have))
    shuffled = list(items)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]
    assert mix(shuffled) == plan  # stable whatever the input order
