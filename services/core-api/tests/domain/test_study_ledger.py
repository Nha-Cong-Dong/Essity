"""T7.10b (US-15 AC4, AC10): the ledger rules, pure."""

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from core_api.domain.study_ledger import (
    LedgerEntry,
    last_studied_days,
    ledger_day,
    studied_on,
    subjects_not_studied,
)

HCM = ZoneInfo("Asia/Ho_Chi_Minh")
A, B = uuid.uuid4(), uuid.uuid4()
S1 = uuid.uuid4()


def test_ac10_day_cut_at_0359_and_0400() -> None:
    # 20:59 UTC = 03:59 HCM, 21:00 UTC = 04:00 HCM
    before = ledger_day(datetime(2026, 10, 22, 20, 59, tzinfo=UTC), HCM, 4)
    after = ledger_day(datetime(2026, 10, 22, 21, 0, tzinfo=UTC), HCM, 4)
    assert before == date(2026, 10, 22)
    assert after == date(2026, 10, 23)


def test_ac4_ledger_says_which_subject_and_section_and_which_not() -> None:
    day = date(2026, 10, 22)
    entries = [LedgerEntry(A, day, S1, 2), LedgerEntry(A, day, None, 1)]
    assert studied_on(entries, day) == {A: {S1}}
    assert subjects_not_studied(entries, day, {A, B}) == {B}
    assert subjects_not_studied(entries, date(2026, 10, 23), {A, B}) == {A, B}


@given(
    st.lists(st.tuples(st.sampled_from([A, B]), st.dates(min_value=date(2026, 1, 1))), max_size=20)
)
def test_ac3_last_studied_is_the_latest_day_per_subject(rows: list[tuple[uuid.UUID, date]]) -> None:
    entries = [LedgerEntry(s, d, None, 1) for s, d in rows]
    last = last_studied_days(entries)
    for subject in {s for s, _ in rows}:
        assert last[subject] == max(d for s, d in rows if s == subject)
    assert set(last) == {s for s, _ in rows}
