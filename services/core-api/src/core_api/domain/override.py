"""What "Chấm sai" writes (T2.18, US-09): the user's verdict replaces the machine's, for the
whole answer. Pure: no database.

The spec leaves two things open (US-09 §9 #1, #2); the simplest rule that keeps the record
honest: every unit of the question gets the user's verdict, and `overall` is the same. So "Thực
ra tôi đúng" on a partial answer makes it correct, and "Thực ra tôi sai" on a right one makes it
incorrect. The understanding score is the machine's opinion of a right answer and is not carried:
a user's override has none.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from core_api.domain.scheduling.rating import Verdict

Choice = Literal["correct", "incorrect"]


@dataclass(frozen=True)
class OverrideGrade:
    overall: Verdict
    units: Mapping[uuid.UUID, Verdict]
    understanding: None = None


def override_of(choice: Choice, unit_ids: Iterable[uuid.UUID]) -> OverrideGrade:
    verdict = Verdict(choice)
    return OverrideGrade(overall=verdict, units={unit_id: verdict for unit_id in unit_ids})
