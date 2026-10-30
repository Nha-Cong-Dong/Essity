"""Mastery per question type and the practice rating (T8.6a, v2 design §8.2 and §16.1 Q-C).

Pure: no database, no I/O. Rules:

- Mastery of a type = mean of its last `config.window` attempts (correct 1, partial 0.5,
  incorrect 0); fewer than `config.min_attempts` attempts: not enough data (`None`).
- Reference time = `config.seconds_per_idea` x rubric ideas until the learner has
  `config.min_timed_correct` correct timed attempts of the type, then the median active time.
- Timing: active = (submitted - served_at) - hidden_ms. A hidden tab (hidden_ms > 0), a negative
  duration, or more than `config.slow_factor` x reference makes the attempt not timing_ok.
- Rating for practice FSRS: incorrect -> Again, partial -> Hard, correct -> Good; Easy only when
  correct, active <= `config.easy_factor` x reference, the previous attempt of the same question was
  correct, and this attempt is timing_ok.
- Sensitivity = median active time of timing_ok attempts in the window vs the reference, as a
  neutral category (never a rank). `reference()` also returns where the reference came from.
- Learned ("thuộc") = retrievability >= `config.learned_retrievability` and the last attempt
  correct.
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Literal

PracticeVerdict = Literal["correct", "partial", "incorrect"]

BANNED_WORDS = (
    "chậm chạp",
    "yếu",
    "kém",
    "tệ",
    "lười",
    "dở",
    "thua",
    "xếp hạng",
    "phạt",
)


@dataclass(frozen=True)
class MasteryConfig:
    """Versioned formula constants; callers pass the config, so a new formula is a new object."""

    version: str = "v1"
    window: int = 10
    min_attempts: int = 3
    seconds_per_idea: float = 60.0
    min_timed_correct: int = 5
    slow_factor: float = 3.0
    easy_factor: float = 0.7
    learned_retrievability: float = 0.9
    sensitivity_min_timed: int = 3
    faster_ratio: float = 0.8
    slower_ratio: float = 1.25


DEFAULT_CONFIG = MasteryConfig()

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


def mastery(
    attempts: Sequence[TypeAttempt], config: MasteryConfig = DEFAULT_CONFIG
) -> float | None:
    """Mean score of the last `config.window` attempts (oldest first); None below the minimum."""
    if len(attempts) < config.min_attempts:
        return None
    recent = attempts[-config.window :]
    return sum(_SCORE[a.verdict] for a in recent) / len(recent)


RefOrigin = Literal["default", "learner"]


@dataclass(frozen=True)
class Reference:
    seconds: float
    origin: RefOrigin


def reference(
    rubric_ideas: int, attempts: Sequence[TypeAttempt], config: MasteryConfig = DEFAULT_CONFIG
) -> Reference:
    """Median active time of the learner's correct timed attempts, once there are enough."""
    times = [
        a.active_seconds
        for a in attempts
        if a.verdict == "correct" and a.timing_ok and a.active_seconds is not None
    ]
    if len(times) >= config.min_timed_correct:
        return Reference(statistics.median(times), "learner")
    return Reference(config.seconds_per_idea * max(rubric_ideas, 1), "default")


def reference_seconds(
    rubric_ideas: int, attempts: Sequence[TypeAttempt], config: MasteryConfig = DEFAULT_CONFIG
) -> float:
    return reference(rubric_ideas, attempts, config).seconds


def active_seconds(served_at: datetime, submitted_at: datetime, hidden_ms: int) -> float:
    return (submitted_at - served_at).total_seconds() - hidden_ms / 1000


def is_timing_ok(
    active: float, hidden_ms: int, reference: float, config: MasteryConfig = DEFAULT_CONFIG
) -> bool:
    return hidden_ms <= 0 and 0 <= active <= config.slow_factor * reference


def rating_for(
    verdict: PracticeVerdict,
    active: float,
    reference: float,
    previous_verdict: PracticeVerdict | None,
    timing_ok: bool,
    config: MasteryConfig = DEFAULT_CONFIG,
) -> PracticeRating:
    if verdict == "incorrect":
        return PracticeRating.AGAIN
    if verdict == "partial":
        return PracticeRating.HARD
    if timing_ok and previous_verdict == "correct" and active <= config.easy_factor * reference:
        return PracticeRating.EASY
    return PracticeRating.GOOD


def is_learned(
    retrievability: float,
    last_verdict: PracticeVerdict | None,
    config: MasteryConfig = DEFAULT_CONFIG,
) -> bool:
    return retrievability >= config.learned_retrievability and last_verdict == "correct"


class Sensitivity(StrEnum):
    NOT_ENOUGH_DATA = "not_enough_data"
    FASTER = "faster"
    NEAR = "near"
    SLOWER = "slower"


def sensitivity(
    attempts: Sequence[TypeAttempt], reference: float, config: MasteryConfig = DEFAULT_CONFIG
) -> Sensitivity:
    """Neutral category from the median active time of timing_ok attempts in the window."""
    times = [
        a.active_seconds
        for a in attempts[-config.window :]
        if a.timing_ok and a.active_seconds is not None
    ]
    if len(times) < config.sensitivity_min_timed or reference <= 0:
        return Sensitivity.NOT_ENOUGH_DATA
    ratio = statistics.median(times) / reference
    if ratio < config.faster_ratio:
        return Sensitivity.FASTER
    if ratio > config.slower_ratio:
        return Sensitivity.SLOWER
    return Sensitivity.NEAR


def _vi_number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _per_question(seconds: float) -> str:
    if seconds < 60:
        return f"{_vi_number(round(seconds))} giây mỗi câu"
    return f"{_vi_number(round(seconds / 60, 1))} phút mỗi câu"


def mastery_line(value: float | None, n: int | None = None) -> str:
    """Neutral Vietnamese mastery line; `n` = attempts counted (default: the window)."""
    if value is None:
        return "chưa đủ dữ liệu"
    total = n if n is not None else DEFAULT_CONFIG.window
    return f"đúng {round(value * total)} trên {total} lần gần nhất"


_SENSITIVITY_WORD = {
    Sensitivity.FASTER: "nhanh hơn mốc",
    Sensitivity.NEAR: "gần mốc",
    Sensitivity.SLOWER: "chậm hơn mốc",
}


def sensitivity_line(category: Sensitivity, reference: float) -> str:
    if category == Sensitivity.NOT_ENOUGH_DATA:
        return "chưa đủ dữ liệu"
    return f"{_SENSITIVITY_WORD[category]}, khoảng {_per_question(reference)}"
