"""Grading verdict -> FSRS rating (ADR-0009, US-06 AC1).

`Easy` is never produced: nothing tells us an answer was "too easy" without asking the user to
rate themselves, which is exactly what the product avoids.
"""

from enum import IntEnum, StrEnum


class Verdict(StrEnum):
    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"
    FORGOT = "forgot"  # the user pressed "Không nhớ"; no AI call


class ReviewRating(IntEnum):
    # Values match FSRS so they can be stored as-is in review_log.rating.
    AGAIN = 1
    HARD = 2
    GOOD = 3


_RATING_BY_VERDICT = {
    Verdict.CORRECT: ReviewRating.GOOD,
    Verdict.PARTIAL: ReviewRating.HARD,
    Verdict.INCORRECT: ReviewRating.AGAIN,
    Verdict.FORGOT: ReviewRating.AGAIN,
}


def rating_for(verdict: Verdict) -> ReviewRating:
    return _RATING_BY_VERDICT[verdict]
