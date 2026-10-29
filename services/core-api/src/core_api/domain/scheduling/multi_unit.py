"""How a multi-unit question moves each unit's schedule (T5.3, PRD AC5 and Q20, US-05 AC9).

The unit is the scheduling item, not the question: every unit takes the rating of its own
verdict. **Q20 tạm** (temporary, until the user settles Q20, PRD line 441): standard FSRS per
unit, and the question level gives no bonus. A rule is a named version; a new rule is a new
entry in `RULES`, an old one is never edited, and `review_log` can be replayed under any of them.
`grade_unit` keeps no "forgot" (it stores incorrect), so a rule cannot tell the two apart.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from uuid import UUID
from zoneinfo import ZoneInfo

from core_api.domain.scheduling.fsrs_adapter import MemoryState
from core_api.domain.scheduling.rating import ReviewRating, Verdict, rating_for
from core_api.domain.scheduling.replay import replay


@dataclass(frozen=True)
class MultiUnitRule:
    version: str
    rating_by_verdict: Mapping[Verdict, ReviewRating]
    temporary: bool
    note: str


Q20_TAM = MultiUnitRule(
    version="q20-tam-1",
    rating_by_verdict=MappingProxyType({verdict: rating_for(verdict) for verdict in Verdict}),
    temporary=True,
    note="Q20 tạm: each unit its own rating, standard FSRS, no level bonus (PRD line 441)",
)
RULES: Mapping[str, MultiUnitRule] = MappingProxyType({Q20_TAM.version: Q20_TAM})
CURRENT_RULE = Q20_TAM


def current_rule() -> MultiUnitRule:
    """The rule live grading and replay use; looked up per call so a test can swap it."""
    return CURRENT_RULE


def rating_under(rule: MultiUnitRule, verdict: Verdict, level: int) -> ReviewRating:
    """The rating of one unit's verdict. `level` is the question's; Q20 tạm ignores it."""
    del level
    return rule.rating_by_verdict[verdict]


def unit_ratings(
    rule: MultiUnitRule, verdicts: Mapping[UUID, Verdict], *, level: int
) -> dict[UUID, ReviewRating]:
    return {unit: rating_under(rule, verdict, level) for unit, verdict in verdicts.items()}


def replay_under_rule(
    outcomes: Iterable[tuple[Verdict, int, datetime]],
    rule: MultiUnitRule,
    *,
    exam_day: date,
    tz: ZoneInfo,
    day_start_hour: int,
) -> MemoryState | None:
    """One unit's state from its (verdict, question level, reviewed_at), oldest first."""
    return replay(
        ((rating_under(rule, verdict, level), at) for verdict, level, at in outcomes),
        exam_day=exam_day,
        tz=tz,
        day_start_hour=day_start_hour,
    )
