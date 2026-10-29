"""T7.10a (v2 design §6.1, Q-A): suggest-next-study rules. Pure."""

import uuid
from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.suggest import (
    Leaf,
    SubjectInput,
    SuggestFilter,
    next_leaf,
    suggest_for_subject,
    suggest_today,
)

TODAY = date(2026, 11, 1)
BANNED = ("phải", "cần", "kịp", "trễ")


def leaf(title: str, weight: float = 10, excluded: bool = False, covered_weight: float = 0) -> Leaf:
    return Leaf(
        id=uuid.uuid4(),
        title=title,
        weight=weight,
        unit="trang",
        excluded=excluded,
        covered_weight=covered_weight,
    )


def subject(
    leaves: list[Leaf],
    exam: date | None = TODAY + timedelta(days=10),
    last: date | None = None,
) -> SubjectInput:
    return SubjectInput(id=uuid.uuid4(), exam_date=exam, last_studied_day=last, leaves=leaves)


def test_first_open_leaf_in_syllabus_order():
    a, b, c = leaf("1", covered_weight=10), leaf("2"), leaf("3")
    assert next_leaf([a, b, c]) is b


def test_hole_from_studying_ahead_is_suggested():
    a, b, c = leaf("1", covered_weight=10), leaf("2"), leaf("3", covered_weight=10)
    s = suggest_for_subject(subject([a, b, c]), TODAY)
    assert s.leaf_id == b.id and s.kind == "next_leaf"


def test_excluded_leaf_is_skipped_and_dropped_from_pace():
    a, b = leaf("1", excluded=True), leaf("2", 5)
    s = suggest_for_subject(subject([a, b]), TODAY)
    assert s.leaf_id == b.id
    assert s.pace.remaining_leaves == 1 and s.pace.remaining_weight == 5


def test_partial_leaf_suggests_remaining_pages():
    a = leaf("1", 10, covered_weight=4)
    s = suggest_for_subject(subject([a]), TODAY)
    assert s.partial and s.remaining_weight == 6 and s.leaf_id == a.id


def test_prerequisite_to_earlier_open_leaf_reorders():
    # leaf 1 is covered, 2 is open, 3 is open and needs... the earlier open 2 comes first anyway;
    # make the reorder visible: 1 (open) needs nothing, 2 needs 1 -> 1; then cover 1 -> 2.
    p = leaf("p", covered_weight=0)
    q = leaf("q")
    q_dep = Leaf(id=q.id, title="q", weight=10, unit="trang", prerequisites=(p.id,))
    assert next_leaf([p, q_dep]) is p


def test_prerequisite_skips_ahead_of_first_open_leaf_is_impossible_but_chain_is_followed():
    # first open leaf `b` has an earlier open prerequisite only if that one is open too, i.e. it
    # would itself be first open; the chain still lands on the earliest open prerequisite.
    a = leaf("a")
    b = Leaf(id=uuid.uuid4(), title="b", weight=10, unit="trang", prerequisites=(a.id,))
    assert next_leaf([a, b]) is a


def test_prerequisite_later_in_syllabus_is_ignored():
    c = leaf("c")
    a = Leaf(id=uuid.uuid4(), title="a", weight=10, unit="trang", prerequisites=(c.id,))
    assert next_leaf([a, c]) is a


def test_prerequisite_already_covered_does_not_reorder():
    done = leaf("done", covered_weight=10)
    b = Leaf(id=uuid.uuid4(), title="b", weight=10, unit="trang", prerequisites=(done.id,))
    assert next_leaf([done, b]) is b


def test_prerequisite_cycle_terminates():
    x, y = uuid.uuid4(), uuid.uuid4()
    lx = Leaf(id=x, title="x", weight=1, unit="trang", prerequisites=(y,))
    ly = Leaf(id=y, title="y", weight=1, unit="trang", prerequisites=(x,))
    assert next_leaf([lx, ly]) in (lx, ly)


def test_fully_studied_is_review_practice():
    leaves = [leaf("1", covered_weight=10), leaf("2", excluded=True)]
    s = suggest_for_subject(subject(leaves), TODAY)
    assert s.kind == "review_practice" and s.leaf_id is None


def test_no_textbook_is_free_session():
    assert suggest_for_subject(subject([]), TODAY).kind == "free_session"
    assert suggest_for_subject(subject([leaf("1", excluded=True)]), TODAY).kind == "free_session"


def test_tightest_first_and_top_two():
    tight = subject([leaf("t", 100)], exam=TODAY + timedelta(days=2))
    mid = subject([leaf("m", 100)], exam=TODAY + timedelta(days=10))
    loose = subject([leaf("l", 100)], exam=TODAY + timedelta(days=50))
    out = suggest_today([loose, mid, tight], TODAY)
    assert [s.subject_id for s in out] == [tight.id, mid.id]


def test_tie_goes_to_longest_ago_never_first():
    old = subject([leaf("a")], last=TODAY - timedelta(days=9))
    new = subject([leaf("b")], last=TODAY - timedelta(days=1))
    never = subject([leaf("c")], last=None)
    out = suggest_today([new, old, never], TODAY)
    assert [s.subject_id for s in out] == [never.id, old.id]


def test_exam_today_uses_one_day():
    s = subject([leaf("a", 30)], exam=TODAY)
    assert suggest_for_subject(s, TODAY).pace.days_left == 0
    assert len(suggest_today([s], TODAY)) == 1


def test_exam_passed_not_suggested_but_button_still_answers():
    s = subject([leaf("a")], exam=TODAY - timedelta(days=1))
    assert suggest_today([s], TODAY) == []
    assert suggest_for_subject(s, TODAY).kind == "next_leaf"


def test_no_exam_date_ranked_last():
    nodate = subject([leaf("a", 1000)], exam=None)
    dated = subject([leaf("b", 1)], exam=TODAY + timedelta(days=90))
    out = suggest_today([nodate, dated], TODAY)
    assert [s.subject_id for s in out] == [dated.id, nodate.id]
    assert out[1].pace.days_left is None


def test_filter_only_subjects_before_ranking():
    a = subject([leaf("a", 1000)], exam=TODAY + timedelta(days=1))
    b = subject([leaf("b", 1)], exam=TODAY + timedelta(days=30))
    out = suggest_today([a, b], TODAY, SuggestFilter(only_subjects={b.id}))
    assert [s.subject_id for s in out] == [b.id]


def test_filter_hidden_until_date():
    a = subject([leaf("a")])
    f = SuggestFilter(hidden_until={a.id: TODAY + timedelta(days=3)})
    assert suggest_today([a], TODAY, f) == []
    assert len(suggest_today([a], TODAY + timedelta(days=3), f)) == 1


def test_pace_text_numbers_only():
    s = subject([leaf("a", 86)], exam=TODAY + timedelta(days=20))
    assert suggest_for_subject(s, TODAY).pace.text == "còn 1 mục (86 trang), 20 ngày"


def test_pace_text_without_exam_or_leaves():
    no_exam = suggest_for_subject(subject([leaf("a", 5)], exam=None), TODAY)
    assert no_exam.pace.text == "còn 1 mục (5 trang)"
    assert suggest_for_subject(subject([], exam=None), TODAY).pace.text == "còn 0 mục"


leaf_st: st.SearchStrategy[Leaf] = st.builds(
    Leaf,
    id=st.builds(uuid.uuid4),
    title=st.text(max_size=5),
    weight=st.floats(min_value=1, max_value=100),
    unit=st.just("trang"),
    excluded=st.booleans(),
    covered_weight=st.floats(min_value=0, max_value=100),
)
subject_st: st.SearchStrategy[SubjectInput] = st.builds(
    SubjectInput,
    id=st.builds(uuid.uuid4),
    exam_date=st.one_of(st.none(), st.dates(TODAY - timedelta(days=5), TODAY + timedelta(days=60))),
    last_studied_day=st.one_of(st.none(), st.dates(TODAY - timedelta(days=30), TODAY)),
    leaves=st.lists(leaf_st, max_size=6),
)


@given(st.lists(subject_st, max_size=8))
def test_property_deterministic_max_two_no_banned_words(subjects: list[SubjectInput]):
    out = suggest_today(subjects, TODAY)
    assert out == suggest_today(list(subjects), TODAY)
    assert len(out) <= 2
    assert len({s.subject_id for s in out}) == len(out)
    for s in out:
        assert not any(w in s.pace.text for w in BANNED)


@pytest.mark.parametrize("w", BANNED)
def test_banned_words_absent_from_sample(w: str):
    s = subject([leaf("a", 12)], exam=TODAY + timedelta(days=3))
    assert w not in suggest_for_subject(s, TODAY).pace.text
