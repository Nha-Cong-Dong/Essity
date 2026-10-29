"""T5.3: a multi-unit question moves each unit's schedule by that unit's own verdict (US-05 AC9,
PRD US-06 AC5). The rule is Q20 tạm: versioned, no level bonus."""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from core_api.domain.scheduling import multi_unit
from core_api.domain.scheduling.multi_unit import (
    CURRENT_RULE,
    Q20_TAM,
    RULES,
    current_rule,
    rating_under,
    replay_under_rule,
    unit_ratings,
)
from core_api.domain.scheduling.rating import ReviewRating, Verdict, rating_for

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
AT = datetime(2026, 10, 1, 13, 0, tzinfo=UTC)
EXAM = date(2026, 11, 20)


# Red when: the question gets one shared rating, or ratings land on the wrong unit.
def test_ac9_three_unit_question_two_right_one_wrong_each_unit_gets_own_rating() -> None:
    a, b, c = (uuid.uuid4() for _ in range(3))
    verdicts = {a: Verdict.CORRECT, b: Verdict.CORRECT, c: Verdict.INCORRECT}
    assert unit_ratings(Q20_TAM, verdicts, level=3) == {
        a: ReviewRating.GOOD,
        b: ReviewRating.GOOD,
        c: ReviewRating.AGAIN,
    }


# Red when: the question level changes a rating (Q20 tạm has no level bonus).
def test_q20_temporary_rule_ignores_question_level() -> None:
    for verdict in Verdict:
        assert {rating_under(Q20_TAM, verdict, level) for level in (1, 2, 3)} == {
            rating_for(verdict)
        }


# Red when: a single-unit question stops matching the plain verdict mapping.
def test_single_unit_question_is_unchanged_by_the_rule() -> None:
    unit = uuid.uuid4()
    for verdict in Verdict:
        assert unit_ratings(CURRENT_RULE, {unit: verdict}, level=1) == {unit: rating_for(verdict)}


# Red when: the current rule is not findable by version or loses its temporary label.
def test_rule_is_versioned_and_current_rule_is_q20_temporary() -> None:
    assert RULES[CURRENT_RULE.version] is CURRENT_RULE
    assert current_rule() is CURRENT_RULE
    assert CURRENT_RULE.temporary and "Q20" in CURRENT_RULE.note


# Red when: replay is not deterministic, or a different rule does not change the schedule.
def test_replay_under_rule_is_deterministic_and_follows_the_rule() -> None:
    harsher = replace(
        Q20_TAM,
        version="test-harsher",
        rating_by_verdict={**Q20_TAM.rating_by_verdict, Verdict.PARTIAL: ReviewRating.AGAIN},
    )
    outcomes = [(Verdict.CORRECT, 1, AT), (Verdict.PARTIAL, 2, AT.replace(day=4))]
    kwargs = {"exam_day": EXAM, "tz": TZ, "day_start_hour": 4}
    first = replay_under_rule(outcomes, Q20_TAM, **kwargs)  # type: ignore[arg-type]
    assert first == replay_under_rule(outcomes, Q20_TAM, **kwargs)  # type: ignore[arg-type]
    assert first != replay_under_rule(outcomes, harsher, **kwargs)  # type: ignore[arg-type]
    assert multi_unit.RULES.get("test-harsher") is None
