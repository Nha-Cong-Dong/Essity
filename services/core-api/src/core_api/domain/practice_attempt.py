"""Timing of a practice attempt (T8.4, US-16 AC5; pure, no database).

The server writes `served_at` once, when the question is first served. The client reports only
`hidden_ms` (time the tab was hidden), which is never trusted: it is clamped to what can be true.
`active_ms = (submitted_at - served_at) - hidden_ms`; the attempt is `timing_ok` only when nothing
was hidden and the active time is within `slow_factor` x the reference (mastery.py owns the rule).
"""

from dataclasses import dataclass
from datetime import datetime

from core_api.domain.mastery import DEFAULT_CONFIG, MasteryConfig, is_timing_ok

MAX_HIDDEN_MS = 24 * 3600 * 1000


@dataclass(frozen=True)
class PracticeTiming:
    hidden_ms: int
    active_ms: int
    timing_ok: bool


def practice_timing(
    served_at: datetime,
    submitted_at: datetime,
    reported_hidden_ms: int,
    reference_seconds: float,
    config: MasteryConfig = DEFAULT_CONFIG,
) -> PracticeTiming:
    """The three values written in the submit UPDATE. Hidden time is clamped to [0, 24 h] and to
    the elapsed time, so `active_ms` is never negative; any positive report still means not ok."""
    elapsed_ms = max(0, round((submitted_at - served_at).total_seconds() * 1000))
    reported = max(0, min(int(reported_hidden_ms), MAX_HIDDEN_MS))
    hidden_ms = min(reported, elapsed_ms)
    active_ms = elapsed_ms - hidden_ms
    ok = is_timing_ok(active_ms / 1000, reported, reference_seconds, config)
    return PracticeTiming(hidden_ms=hidden_ms, active_ms=active_ms, timing_ok=ok)
