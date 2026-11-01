"""T8.4 (US-16 AC5, PLAN T8.4): the timing of a practice attempt. The server writes `served_at`;
the client only reports `hidden_ms`. active = (submitted - served) - hidden; `timing_ok` is false
when anything was hidden or the active time is over 3x the reference."""

from datetime import UTC, datetime, timedelta

from core_api.domain.practice_attempt import MAX_HIDDEN_MS, practice_timing

SERVED = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def timing(seconds: float, hidden_ms: int, reference: float = 100.0):
    return practice_timing(SERVED, SERVED + timedelta(seconds=seconds), hidden_ms, reference)


def test_active_ms_is_elapsed_minus_hidden() -> None:
    # Red when: the formula is not (submit - served_at) - hidden_ms.
    t = timing(60, 10_000)
    assert (t.hidden_ms, t.active_ms) == (10_000, 50_000)


def test_no_hidden_time_and_quick_is_ok() -> None:
    # Red when: a clean, fast attempt is not timing_ok.
    t = timing(60, 0)
    assert (t.active_ms, t.timing_ok) == (60_000, True)


def test_any_hidden_time_is_not_ok() -> None:
    # Red when: hidden_ms > 0 still counts as measured.
    assert timing(60, 1).timing_ok is False


def test_exactly_three_times_the_reference_is_ok_and_beyond_is_not() -> None:
    # Red when: the limit is off by one side (3x allowed, over 3x not).
    assert timing(300, 0).timing_ok is True
    assert timing(300.001, 0).timing_ok is False


def test_hidden_is_clamped_to_the_elapsed_time() -> None:
    # Red when: a client claiming more hidden time than elapsed drives active_ms negative.
    t = timing(10, 60_000)
    assert (t.hidden_ms, t.active_ms, t.timing_ok) == (10_000, 0, False)


def test_negative_and_huge_hidden_are_clamped() -> None:
    # Red when: a negative value adds time, or a huge one is stored as sent.
    assert timing(10, -5_000).hidden_ms == 0
    assert timing(10, -5_000).timing_ok is True
    far = practice_timing(SERVED, SERVED + timedelta(days=3), 10**12, 100.0)
    assert far.hidden_ms == MAX_HIDDEN_MS
    assert far.timing_ok is False


def test_submit_before_served_counts_as_zero_elapsed() -> None:
    # Red when: a clock skew gives negative active_ms (the column has CHECK >= 0).
    t = practice_timing(SERVED, SERVED - timedelta(seconds=5), 0, 100.0)
    assert t.active_ms == 0
