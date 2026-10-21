"""T1.17: the baseline's rules, without a database (US-11 AC1, AC2, AC5; plan B1, B4, B5)."""

from datetime import UTC, datetime, timedelta

from core_api.domain.baseline import (
    EDIT_WINDOW,
    LATE_AFTER,
    MAX_SKIPS,
    editable_until,
    is_late,
    is_locked,
    needs_baseline,
)

VERIFIED = datetime(2026, 10, 1, 20, 0, tzinfo=UTC)


def test_windows_are_seven_days() -> None:
    assert EDIT_WINDOW == LATE_AFTER == timedelta(days=7)
    assert MAX_SKIPS == 2


def test_ac2_entered_within_seven_days_of_verifying_is_not_late() -> None:
    assert is_late(VERIFIED, VERIFIED) is False
    assert is_late(VERIFIED + timedelta(days=7), VERIFIED) is False


def test_ac2_entered_more_than_seven_days_after_verifying_is_late() -> None:
    assert is_late(VERIFIED + timedelta(days=7, seconds=1), VERIFIED) is True


def test_ac5_editable_until_seven_days_after_entering() -> None:
    assert editable_until(VERIFIED) == VERIFIED + timedelta(days=7)


def test_ac5_locked_from_seven_days_after_entering() -> None:
    assert is_locked(VERIFIED, VERIFIED + timedelta(days=7) - timedelta(seconds=1)) is False
    assert is_locked(VERIFIED, VERIFIED + timedelta(days=7)) is True


def test_ac1_verified_account_without_baseline_needs_one() -> None:
    assert needs_baseline(verified=True, has_baseline=False, skips=0) is True


def test_ac1_unverified_account_is_not_asked_yet() -> None:
    assert needs_baseline(verified=False, has_baseline=False, skips=0) is False


def test_ac2_asked_again_after_one_skip_then_never() -> None:
    assert needs_baseline(verified=True, has_baseline=False, skips=1) is True
    assert needs_baseline(verified=True, has_baseline=False, skips=2) is False


def test_account_with_baseline_is_not_asked() -> None:
    assert needs_baseline(verified=True, has_baseline=True, skips=0) is False
