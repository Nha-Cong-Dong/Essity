"""The question ladder (T5.2, US-03 AC3, PRD US-04b AC3): recognise -> apply -> deep-apply. Pure.

A question of level 2 may be asked only when every unit it checks has been answered Correct at
level 1 at least `min_correct_level1` times; level 3 only when every unit it checks has been
Correct at level 2 at least `min_correct_level2` times. The thresholds are Q19's (the user's, still
open) and live in `core_api/data/ladder.json`, versioned: changing them edits that file, not code.
Q19 tạm: 1 and 1, as PRD AC3 words it.

`correct` maps (unit id, question level) to the Correct answers so far (`TodayRepository`).
A unit whose questions are all above its level falls back to its lowest level instead of
dropping out of today (the choice before the ladder).
"""

import json
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path


@dataclass(frozen=True)
class LadderConfig:
    version: int
    min_correct_level1: int  # per unit, before it is asked at level 2
    min_correct_level2: int  # per unit, before a question on it is asked at level 3


@dataclass(frozen=True)
class LadderQuestion:
    question_id: uuid.UUID
    level: int
    unit_ids: frozenset[uuid.UUID]
    created_at: datetime


def load_ladder_config(path: Path | None = None) -> LadderConfig:
    """The shipped `ladder.json`, or the file at `path`. ValueError when malformed."""
    raw = (
        path.read_text("utf-8")
        if path is not None
        else files("core_api.data").joinpath("ladder.json").read_text("utf-8")
    )
    body: object = json.loads(raw)
    fields: dict[str, object] = (
        {str(k): v for k, v in body.items()} if isinstance(body, dict) else {}  # type: ignore[reportUnknownVariableType]
    )
    values: list[int] = []
    for key in ("version", "min_correct_level1", "min_correct_level2"):
        value = fields.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"ladder config: {key} must be an integer >= 1")
        values.append(value)
    return LadderConfig(*values)


def is_eligible(
    question: LadderQuestion, correct: Mapping[tuple[uuid.UUID, int], int], config: LadderConfig
) -> bool:
    if question.level <= 1:
        return True
    if not question.unit_ids:
        return False
    needed = config.min_correct_level1 if question.level == 2 else config.min_correct_level2
    below = question.level - 1
    return all(correct.get((unit, below), 0) >= needed for unit in question.unit_ids)


def choose_for_unit(
    unit_id: uuid.UUID,
    questions: Collection[LadderQuestion],
    correct: Mapping[tuple[uuid.UUID, int], int],
    config: LadderConfig,
) -> LadderQuestion | None:
    """The unit's question: highest eligible level, oldest first inside a level; none eligible:
    the lowest level there is; no question at all: None."""
    mine = [q for q in questions if unit_id in q.unit_ids]
    if not mine:
        return None
    eligible = [q for q in mine if is_eligible(q, correct, config)]
    if eligible:
        top = max(q.level for q in eligible)
        return min((q for q in eligible if q.level == top), key=_oldest)
    low = min(q.level for q in mine)
    return min((q for q in mine if q.level == low), key=_oldest)


def _oldest(question: LadderQuestion) -> tuple[datetime, uuid.UUID]:
    return question.created_at, question.question_id
