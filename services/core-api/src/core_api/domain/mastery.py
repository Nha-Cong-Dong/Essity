"""Mastery per question type and the practice rating (T8.6a, v2 design §8.2 and §16.1 Q-C).

Pure: no database, no I/O. Rules:

- Mastery of a type = mean of its last `WINDOW` attempts (correct 1, partial 0.5, incorrect 0);
  fewer than `MIN_ATTEMPTS` attempts: not enough data (`None`).
- Reference time = `SECONDS_PER_IDEA` x rubric ideas until the learner has `MIN_TIMED_CORRECT`
  correct timed attempts of the type, then the median active time of those.
- Timing: active = (submitted - served_at) - hidden_ms. A hidden tab (hidden_ms > 0), a negative
  duration, or more than `SLOW_FACTOR` x reference makes the attempt not timing_ok.
- Rating for practice FSRS: incorrect -> Again, partial -> Hard, correct -> Good; Easy only when
  correct, active <= `EASY_FACTOR` x reference, the previous attempt of the same question was
  correct, and this attempt is timing_ok.
- Learned ("thuộc") = retrievability >= `LEARNED_RETRIEVABILITY` and the last attempt correct.
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Literal

PracticeVerdict = Literal["correct", "partial", "incorrect"]

WINDOW = 10
MIN_ATTEMPTS = 3
SECONDS_PER_IDEA = 60.0
MIN_TIMED_CORRECT = 5
SLOW_FACTOR = 3.0
EASY_FACTOR = 0.7
LEARNED_RETRIEVABILITY = 0.9

_SCORE: dict[PracticeVerdict, float] = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}


class PracticeRating(IntEnum):
    # Values match FSRS ratings.
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


@dataclass(frozen=True)
class TypeAttempt:
    """One graded attempt of a question of the type; `active_seconds` is None when not timed."""

    verdict: PracticeVerdict
    active_seconds: float | None = None
    timing_ok: bool = False


def mastery(attempts: Sequence[TypeAttempt]) -> float | None:
    """Mean score of the last `WINDOW` attempts (oldest first); None below `MIN_ATTEMPTS`."""
    if len(attempts) < MIN_ATTEMPTS:
        return None
    recent = attempts[-WINDOW:]
    return sum(_SCORE[a.verdict] for a in recent) / len(recent)


def reference_seconds(rubric_ideas: int, attempts: Sequence[TypeAttempt]) -> float:
    """Median active time of the learner's correct timed attempts, once there are enough."""
    times = [
        a.active_seconds
        for a in attempts
        if a.verdict == "correct" and a.timing_ok and a.active_seconds is not None
    ]
    if len(times) >= MIN_TIMED_CORRECT:
        return statistics.median(times)
    return SECONDS_PER_IDEA * max(rubric_ideas, 1)


def active_seconds(served_at: datetime, submitted_at: datetime, hidden_ms: int) -> float:
    return (submitted_at - served_at).total_seconds() - hidden_ms / 1000


def is_timing_ok(active: float, hidden_ms: int, reference: float) -> bool:
    return hidden_ms <= 0 and 0 <= active <= SLOW_FACTOR * reference


def rating_for(
    verdict: PracticeVerdict,
    active: float,
    reference: float,
    previous_verdict: PracticeVerdict | None,
    timing_ok: bool,
) -> PracticeRating:
    if verdict == "incorrect":
        return PracticeRating.AGAIN
    if verdict == "partial":
        return PracticeRating.HARD
    if timing_ok and previous_verdict == "correct" and active <= EASY_FACTOR * reference:
        return PracticeRating.EASY
    return PracticeRating.GOOD


def is_learned(retrievability: float, last_verdict: PracticeVerdict | None) -> bool:
    return retrievability >= LEARNED_RETRIEVABILITY and last_verdict == "correct"
