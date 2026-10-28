"""T5.4 (US-07 AC1, AC2): the reason a question is in the session, from the schedule alone."""

from datetime import UTC, datetime, timedelta

from core_api.domain.explain import explain
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, MemoryState, Phase

NOW = datetime(2026, 11, 2, 13, 0, tzinfo=UTC)


def state(stability: float, days_ago: float) -> MemoryState:
    return MemoryState(
        phase=Phase.REVIEW,
        step=None,
        stability=stability,
        difficulty=5.0,
        due=NOW,
        last_review=NOW - timedelta(days=days_ago),
    )


# US-07 AC2. Red when: the numbers are not the model's (retrievability) or the elapsed days.
def test_us07_ac2_review_reason_matches_the_schedule() -> None:
    s = state(10.0, 6)
    reason = explain([s], NOW)
    assert reason.kind == "review"
    assert reason.days_since_last == 6
    assert reason.retrievability == FsrsScheduler().retrievability(s, NOW)


# US-07 AC2. Red when: a question of several units cites a unit other than the weakest.
def test_us07_ac2_cites_the_unit_least_likely_remembered() -> None:
    fresh, old = state(30.0, 2), state(5.0, 12)
    reason = explain([fresh, old], NOW)
    assert reason.days_since_last == 12
    assert reason.retrievability == FsrsScheduler().retrievability(old, NOW)


# US-07 AC1. Red when: a question never reviewed has no reason.
def test_us07_ac1_new_question_has_its_own_reason() -> None:
    reason = explain([], NOW)
    assert (reason.kind, reason.retrievability, reason.days_since_last) == ("new", None, None)


# Red when: partial days round up, or a last review "in the future" gives a negative count.
def test_days_are_whole_and_never_negative() -> None:
    assert explain([state(10.0, 2.9)], NOW).days_since_last == 2
    assert explain([state(10.0, -0.5)], NOW).days_since_last == 0
