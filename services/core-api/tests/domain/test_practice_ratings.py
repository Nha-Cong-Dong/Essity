"""T8.3: the step by a known rating and the replay of a rating log (ADR-0029, US-16 AC7,
US-06 AC7). `practice_log` keeps only the rating, so the rebuilt state must equal the live one."""

from datetime import UTC, datetime, timedelta

import pytest

from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler
from core_api.domain.scheduling.practice import (
    Attempt,
    apply,
    apply_rating,
    replay_ratings,
    verdict_of,
)
from core_api.domain.scheduling.rating import ReviewRating

T0 = datetime(2026, 10, 1, 13, 0, tzinfo=UTC)
CHAIN = [1, 3, 4, 2, 1, 3, 4, 4]


@pytest.mark.parametrize(
    ("rating", "verdict"),
    [
        (PracticeRating.AGAIN, "incorrect"),
        (PracticeRating.HARD, "partial"),
        (PracticeRating.GOOD, "correct"),
        (PracticeRating.EASY, "correct"),
    ],
)
def test_verdict_of_rating(rating: PracticeRating, verdict: str) -> None:
    # Red when: the verdict a rating stands for is wrong (Easy and Good are both correct).
    assert verdict_of(rating) == verdict


def test_replay_ratings_equals_live_apply_every_field() -> None:
    # Red when: the live step and the replay of its log differ in one field (US-06 AC7).
    state = None
    live: list[tuple[PracticeRating, datetime]] = []
    for i, raw in enumerate(CHAIN):
        at = T0 + timedelta(days=3 * i)
        state = apply_rating(state, PracticeRating(raw), at)
        live.append((PracticeRating(raw), at))
    assert replay_ratings(live) == state


def test_apply_goes_through_apply_rating() -> None:
    # Red when: `apply` computes its own step instead of the one the replay uses.
    first = apply(None, Attempt("correct", 50.0, 100.0, True, T0))
    second = Attempt("correct", 40.0, 100.0, True, T0 + timedelta(days=3))
    live = apply(first, second)
    assert live.memory.last_review == second.at
    assert replay_ratings([(PracticeRating.GOOD, T0), (PracticeRating.EASY, second.at)]) == live


def test_replay_ratings_empty_is_none() -> None:
    assert replay_ratings([]) is None


def test_card_rating_has_no_easy_practice_does() -> None:
    # Red when: ReviewRating gains Easy (ADR-0009), or the adapter refuses PracticeRating.EASY.
    assert "EASY" not in ReviewRating.__members__
    assert FsrsScheduler().review(None, PracticeRating.EASY, T0).stability > 0
