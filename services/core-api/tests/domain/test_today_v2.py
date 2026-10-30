"""T7.11a (v2 design §6.2): Today v2 composer. Pure."""

import dataclasses
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from core_api.domain.suggest import Leaf, SubjectInput, SuggestFilter
from core_api.domain.today import MAX_QUESTIONS
from core_api.domain.today_v2 import (
    EMPTY_LINKS,
    REASON_ALL_STUDIED,
    REASON_EXAMS_OVER,
    REASON_FILTERED,
    REASON_NO_SUBJECTS,
    REASON_NO_SYLLABUS,
    DraftSession,
    PracticeLine,
    PracticePart,
    ReviewCard,
    TodayInputs,
    TodayV2,
    compose,
)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=TZ)  # learning day 2026-11-02 (day starts 04:00)
TODAY = date(2026, 11, 2)
START_HOUR = 4
BANNED = (
    "lại quên", "lười", "bỏ lỡ", "thất bại", "kém", "chuỗi", "streak", "tụt", "mất chuỗi",
    "đáng lẽ", "phải", "cần", "kịp", "trễ", "tồn đọng",
)  # fmt: skip


def _has_banned(text: str) -> bool:
    return any(
        re.search(rf"(?<![^\W\d_]){re.escape(w)}(?![^\W\d_])", text, re.IGNORECASE) for w in BANNED
    )


def leaf(title: str, covered: float = 0, weight: float = 10) -> Leaf:
    return Leaf(uuid.uuid4(), title, weight, "trang", covered_weight=covered)


def subject(leaves: list[Leaf], exam: date | None = TODAY + timedelta(days=10)) -> SubjectInput:
    return SubjectInput(uuid.uuid4(), exam, None, leaves)


def card(
    subject_id: uuid.UUID,
    *,
    due: datetime | None = None,
    created: datetime | None = None,
    recall: float = 0.5,
) -> ReviewCard:
    return ReviewCard(
        uuid.uuid4(),
        subject_id,
        created or NOW - timedelta(days=5),
        due or NOW - timedelta(hours=1),
        recall,
    )


def inputs(subjects: list[SubjectInput], **kw: object) -> TodayInputs:
    names = {s.id: f"Môn {i}" for i, s in enumerate(subjects)}
    base: dict[str, object] = {
        "now": NOW,
        "tz": TZ,
        "day_start_hour": START_HOUR,
        "cards": [],
    }
    return TodayInputs(subjects=subjects, subject_names=names, **{**base, **kw})  # type: ignore[arg-type]


def all_strings(today: TodayV2) -> list[str]:
    out = [i.line for i in today.unfinished] + [i.why for i in today.review.items]
    out += [i.reason for i in today.next_study.items]
    out += [i.suggestion.pace.text for i in today.next_study.items]
    if today.next_study.empty_reason:
        out.append(today.next_study.empty_reason)
    return out


# --- next_study (US-03 AC3, US-15 AC1-AC3) ---


def test_next_study_top_two_with_reason():  # US-03 AC3
    subs = [subject([leaf(f"m{i}")], exam=TODAY + timedelta(days=5 + i)) for i in range(3)]
    today = compose(inputs(subs))
    assert len(today.next_study.items) == 2
    assert today.next_study.empty_reason is None and today.next_study.links == ()
    assert all(i.reason for i in today.next_study.items)
    assert today.next_study.items[0].subject_name == "Môn 0"


def test_reason_variants():  # US-15 AC1
    partial = subject([leaf("3.2", covered=4)])
    hole = subject([leaf("3.1"), leaf("3.2", covered=10)])
    plain = subject([leaf("1.1")])
    for sub, text in (
        (partial, "Bạn học dở mục 3.2: còn 6 trang."),
        (hole, "Mục 3.1 chưa học; bạn đã học tới 3.2."),
        (plain, "Mục 1.1 là mục tiếp theo trong đề cương."),
    ):
        got = compose(inputs([sub])).next_study.items[0].reason
        assert got == text


# --- US-15 AC11: three no-suggestion cases + extras ---


def test_ac11_all_exams_over():  # US-15 AC11
    subs = [subject([leaf("a")], exam=TODAY - timedelta(days=1))]
    ns = compose(inputs(subs)).next_study
    assert ns.items == () and ns.empty_reason == REASON_EXAMS_OVER and ns.links == EMPTY_LINKS


def test_ac11_no_syllabus():  # US-15 AC11
    ns = compose(inputs([subject([])])).next_study
    assert ns.items == () and ns.empty_reason == REASON_NO_SYLLABUS and ns.links == EMPTY_LINKS


def test_ac11_syllabus_all_studied():  # US-15 AC11
    ns = compose(inputs([subject([leaf("a", covered=10)])])).next_study
    assert ns.items == () and ns.empty_reason == REASON_ALL_STUDIED and ns.links == EMPTY_LINKS


def test_empty_no_subjects_and_filtered():  # US-15 AC11
    assert compose(inputs([])).next_study.empty_reason == REASON_NO_SUBJECTS
    sub = subject([leaf("a")])
    flt = SuggestFilter(only_subjects={uuid.uuid4()})
    ns = compose(inputs([sub], filters=flt)).next_study
    assert ns.empty_reason == REASON_FILTERED and ns.links == EMPTY_LINKS


def test_empty_priority_exam_over_beats_others():  # US-15 AC11
    subs = [
        subject([], exam=TODAY - timedelta(days=2)),
        subject([leaf("a", covered=10)], exam=None),
    ]
    assert compose(inputs(subs)).next_study.empty_reason == REASON_ALL_STUDIED
    subs = [subject([], exam=TODAY - timedelta(days=2)), subject([], exam=None)]
    assert compose(inputs(subs)).next_study.empty_reason == REASON_NO_SYLLABUS


# --- review (US-03 AC4, AC7) ---


def test_review_due_only_with_why_and_riskiest_first():  # US-03 AC4
    s = subject([leaf("a")])
    risky = card(s.id, recall=0.2)
    safe = card(s.id, recall=0.9)
    future = card(s.id, due=NOW + timedelta(days=3))
    review = compose(inputs([s], cards=[safe, future, risky])).review
    assert [i.card_id for i in review.items] == [risky.card_id, safe.card_id]
    assert review.items[0].why == "Đến hạn ôn; khả năng nhớ khoảng 20%."
    assert review.minutes == 3  # ceil(2 * 1.5)


def test_review_cap_20_cards_30_minutes():  # US-03 AC4, AC5
    s = subject([leaf("a")])
    cards = [card(s.id, recall=i / 1000) for i in range(200)]
    review = compose(inputs([s], cards=cards)).review
    assert len(review.items) == MAX_QUESTIONS == 20
    assert review.minutes == 30
    assert not hasattr(review, "total") and not hasattr(review, "backlog")


def test_review_exam_near_ranks_first():  # US-03 AC4 (two subjects, one near exam)
    near = subject([leaf("a")], exam=TODAY + timedelta(days=1))
    far = subject([leaf("b")], exam=TODAY + timedelta(days=60))
    c_far = card(far.id, recall=0.5)
    c_near = card(near.id, recall=0.5)
    review = compose(inputs([far, near], cards=[c_far, c_near])).review
    assert review.items[0].card_id == c_near.card_id


def test_review_empty_shows_next_due_day():  # US-03 AC7
    s = subject([leaf("a")])
    later = card(s.id, due=NOW + timedelta(days=3, hours=2))
    sooner = card(s.id, due=NOW + timedelta(days=2))
    review = compose(inputs([s], cards=[later, sooner])).review
    assert review.items == () and review.minutes == 0
    assert review.next_due_day == TODAY + timedelta(days=2)


def test_review_has_no_next_day_when_something_due():  # US-03 AC7
    s = subject([leaf("a")])
    review = compose(
        inputs([s], cards=[card(s.id), card(s.id, due=NOW + timedelta(days=4))])
    ).review
    assert len(review.items) == 1 and review.next_due_day is None


# --- learning-day boundaries (ADR-0009) ---


def test_card_saved_today_enters_next_learning_day():  # US-02b AC12, US-03 AC4
    s = subject([leaf("a")])
    fresh = card(s.id, created=NOW - timedelta(hours=1), due=NOW - timedelta(hours=1))
    review = compose(inputs([s], cards=[fresh])).review
    assert review.items == () and review.new_saved_today
    assert review.next_due_day == TODAY + timedelta(days=1)
    tomorrow = compose(inputs([s], cards=[fresh], now=NOW + timedelta(days=1))).review
    assert [i.card_id for i in tomorrow.items] == [fresh.card_id] and not tomorrow.new_saved_today


def test_boundary_before_day_start_still_yesterday():  # ADR-0009
    s = subject([leaf("a")])
    saved = datetime(2026, 11, 2, 1, 30, tzinfo=TZ)  # learning day 11-01
    c = card(s.id, created=saved, due=saved)
    at_0359 = datetime(2026, 11, 2, 3, 59, tzinfo=TZ)
    at_0400 = datetime(2026, 11, 2, 4, 0, tzinfo=TZ)
    # 03:59 is still learning day 11-01: the card was saved that day, so it is not in yet
    assert compose(inputs([s], cards=[c], now=at_0359)).review.items == ()
    assert len(compose(inputs([s], cards=[c], now=at_0400)).review.items) == 1


def test_boundary_due_just_before_and_after_day_end():  # ADR-0009
    s = subject([leaf("a")])
    end = datetime(2026, 11, 3, 4, 0, tzinfo=TZ)  # end of learning day 11-02
    inside = card(s.id, due=end - timedelta(minutes=1))
    outside = card(s.id, due=end)
    review = compose(inputs([s], cards=[inside, outside])).review
    assert [i.card_id for i in review.items] == [inside.card_id]
    assert review.next_due_day is None


def test_day_is_in_utc_aware_now():  # ADR-0009
    s = subject([leaf("a")])
    utc_now = datetime(2026, 11, 1, 21, 30, tzinfo=UTC)  # 04:30 local on 11-02
    assert compose(inputs([s], now=utc_now)).day == TODAY


# --- unfinished (US-03 AC1) ---


def test_unfinished_one_line_per_session_links_session():  # US-03 AC1
    s = subject([leaf("a")])
    drafts = DraftSession(uuid.uuid4(), s.id, 4, False, NOW - timedelta(hours=2))
    both = DraftSession(uuid.uuid4(), s.id, 2, True, NOW - timedelta(hours=1))
    pending = DraftSession(uuid.uuid4(), s.id, 0, True, NOW - timedelta(hours=3))
    done = DraftSession(uuid.uuid4(), s.id, 0, False, NOW)
    out = compose(inputs([s], sessions=[drafts, both, pending, done])).unfinished
    assert [i.session_id for i in out] == [pending.session_id, drafts.session_id, both.session_id]
    assert out[1].line == "Môn 0: còn 4 thẻ nháp chưa duyệt."
    assert "chờ lượt AI" in out[0].line and "chờ lượt AI" in out[2].line


def test_unfinished_never_a_backlog_count():  # US-03 AC4
    s = subject([leaf("a")])
    sessions = [DraftSession(uuid.uuid4(), s.id, 1, False, NOW) for _ in range(30)]
    out = compose(inputs([s], sessions=sessions)).unfinished
    assert len(out) == 30 and not any("30" in i.line for i in out)
    assert not hasattr(compose(inputs([s])), "total")


# --- copy (US-03 AC10, US-15 AC5, AC11) ---


def test_copy_has_no_banned_words():  # US-03 AC10, US-15 AC5
    s1 = subject([leaf("3.1"), leaf("3.2", covered=10)])
    s2 = subject([leaf("1.1", covered=3)])
    sess = [
        DraftSession(uuid.uuid4(), s1.id, 3, True, NOW),
        DraftSession(uuid.uuid4(), s2.id, 0, True, NOW),
    ]
    full = compose(inputs([s1, s2], cards=[card(s1.id)], sessions=sess))
    empties = [
        compose(inputs([subject([leaf("a")], exam=TODAY - timedelta(days=1))])),
        compose(inputs([subject([])])),
        compose(inputs([subject([leaf("a", covered=10)])])),
        compose(inputs([])),
        compose(inputs([s1], filters=SuggestFilter(only_subjects=set()))),
    ]
    for today in [full, *empties]:
        assert all_strings(today)
        assert not any(_has_banned(x) for x in all_strings(today)), all_strings(today)


def test_banned_regex_is_unicode_safe():  # US-03 AC10
    assert _has_banned("Bạn đã trễ.")
    assert not _has_banned("Tệp cần-thiết".replace("cần-", "xx"))
    assert not _has_banned("kịpx")


# --- practice extension point (T8.5) ---


def test_practice_part_leaves_other_parts_equal():  # US-03 AC6 (T8.5 hook)
    s = subject([leaf("a")])
    c = card(s.id)
    base = compose(inputs([s], cards=[c]))
    part = PracticePart((PracticeLine(s.id, 5, 2),))
    extended = compose(inputs([s], cards=[c], practice=part))
    assert base.practice is None and extended.practice == part
    assert dataclasses.replace(extended, practice=None) == base
