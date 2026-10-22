"""The baseline's rules (US-11): when it counts as late, when it locks, when to ask for it.

Pure functions: the caller passes the instants, so tests need no clock and no database.
"""

from datetime import datetime, timedelta

# Entered more than this after verifying the email: marked late (AC2). "First day of use" is
# read as the first seven days, as DESIGN §6.12 puts it (plan B4).
LATE_AFTER = timedelta(days=7)
# Editable for this long after entering it, then locked, so the baseline cannot be tuned to make
# the results look better (AC5).
EDIT_WINDOW = timedelta(days=7)
# "Later" on the baseline screen: asked once more, then never (AC2, plan B1).
MAX_SKIPS = 2


def is_late(entered_at: datetime, verified_at: datetime) -> bool:
    return entered_at - verified_at > LATE_AFTER


def editable_until(entered_at: datetime) -> datetime:
    return entered_at + EDIT_WINDOW


def is_locked(entered_at: datetime, now: datetime) -> bool:
    return now >= editable_until(entered_at)


def needs_baseline(*, verified: bool, has_baseline: bool, skips: int) -> bool:
    """Whether web shows the baseline screen. Not before the email is verified: web sends an
    unverified account to check its email first."""
    return verified and not has_baseline and skips < MAX_SKIPS
