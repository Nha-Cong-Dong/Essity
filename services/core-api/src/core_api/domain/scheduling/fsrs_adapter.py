"""The only module that imports py-fsrs (ADR-0009). Everything else uses `MemoryState`.

Departures from py-fsrs defaults, all chosen so that "due" works in whole learning days:

- No fuzzing. Fuzz uses the global RNG, and `memory_state` must be rebuilt from `review_log`
  field for field (T2.6). Determinism matters more than spreading out the load.
- No learning steps. The defaults (1 and 10 minutes) suit flashcard apps that re-show a card in
  the same sitting; here a session asks each question once. A new unit goes straight to Review.
- One relearning step of 1 day instead of 10 minutes. Without any step, a lapse on a well-known
  unit is scheduled days later (it keeps a high stability), which breaks US-06 AC2: a wrong answer
  must come back within one day.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from fsrs import Card, Rating, Scheduler, State
from fsrs.scheduler import DEFAULT_PARAMETERS

from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.rating import ReviewRating

DEFAULT_DESIRED_RETENTION = 0.9
RELEARNING_STEPS = (timedelta(days=1),)


class Phase(StrEnum):
    REVIEW = "review"
    RELEARNING = "relearning"  # answered wrong; comes back after the relearning step


_STATE_BY_PHASE = {Phase.REVIEW: State.Review, Phase.RELEARNING: State.Relearning}
_PHASE_BY_STATE = {state: phase for phase, state in _STATE_BY_PHASE.items()}


@dataclass(frozen=True)
class MemoryState:
    """FSRS state of one (unit, facet), mirroring the memory_state table. All times are UTC."""

    phase: Phase
    step: int | None  # index into RELEARNING_STEPS while relearning, else None
    stability: float
    difficulty: float
    due: datetime
    last_review: datetime


class FsrsScheduler:
    def __init__(
        self,
        parameters: Sequence[float] = DEFAULT_PARAMETERS,
        desired_retention: float = DEFAULT_DESIRED_RETENTION,
    ) -> None:
        self._scheduler = Scheduler(
            parameters=parameters,
            desired_retention=desired_retention,
            learning_steps=(),
            relearning_steps=RELEARNING_STEPS,
            enable_fuzzing=False,
        )

    def review(
        self,
        state: MemoryState | None,
        rating: ReviewRating | PracticeRating,
        reviewed_at: datetime,
    ) -> MemoryState:
        """Apply one review. `state` is None for a unit that has never been reviewed.

        Cards pass `ReviewRating` (no Easy, ADR-0009); practice questions may pass `Easy`.
        """
        card, _ = self._scheduler.review_card(_to_card(state), Rating(rating), _utc(reviewed_at))
        assert card.stability is not None
        assert card.difficulty is not None
        assert card.last_review is not None
        return MemoryState(
            phase=_PHASE_BY_STATE[card.state],  # Learning is unreachable without learning steps
            step=card.step,
            stability=card.stability,
            difficulty=card.difficulty,
            due=card.due,
            last_review=card.last_review,
        )

    def retrievability(self, state: MemoryState, at: datetime) -> float:
        """Predicted probability of recalling the unit at `at` (US-07)."""
        return self._scheduler.get_card_retrievability(_to_card(state), _utc(at))


def _to_card(state: MemoryState | None) -> Card:
    # card_id is only used by py-fsrs for its own ReviewLog, which we discard. Passing it avoids
    # the 1 ms sleep Card() does when generating one.
    if state is None:
        return Card(card_id=0)
    return Card(
        card_id=0,
        state=_STATE_BY_PHASE[state.phase],
        step=state.step,
        stability=state.stability,
        difficulty=state.difficulty,
        due=state.due,
        last_review=state.last_review,
    )


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return moment.astimezone(UTC)
