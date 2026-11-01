"""T8.4 tester (US-16 AC5): clock skew between serve and submit, a case the branch tests check
only for `active_ms`. The columns carry CHECK hidden_ms >= 0, and any reported hidden time means
the attempt was not measured."""

from datetime import UTC, datetime, timedelta

from core_api.domain.practice_attempt import practice_timing

SERVED = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def test_tester_skewed_clock_with_hidden_time_is_zero_and_not_ok() -> None:
    # Red when: a submit before served_at (clock skew) gives a negative hidden_ms (the column
    # refuses it and the submit 500s), or a reported hidden tab is still timing_ok because the
    # clamped value (0) is used instead of the report.
    t = practice_timing(SERVED, SERVED - timedelta(seconds=5), 3_000, 100.0)
    assert (t.hidden_ms, t.active_ms, t.timing_ok) == (0, 0, False)
