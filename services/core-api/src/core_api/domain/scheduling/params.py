"""Per-user FSRS parameters: versions, rollback, and a fit from the user's own reviews (T5.9).

`user.fsrs_params` (JSONB) holds the history `{"versions": [{"version", "parameters", ...}]}` and
`user.fsrs_params_version` says which one is active; empty means the FSRS defaults (ADR-0009).
Keeping the history in the existing column avoids a new table. A rollback moves the active
version back; a later fit appends a version with a new, higher number.

py-fsrs's own `Optimizer` needs torch, which is not a dependency (and is far too heavy for this
deploy), so the fit here is the simplest documented approach instead: coordinate search over
three parameter groups that matter most for a short history, minimising the log-loss of the
recall FSRS predicts at each repeat review (the same loss py-fsrs minimises). The other 17
parameters stay at their defaults, so a fit can never wander far from a sane scheduler.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from core_api.domain.scheduling.fsrs_adapter import (
    DEFAULT_PARAMETERS,
    LOWER_BOUNDS_PARAMETERS,
    UPPER_BOUNDS_PARAMETERS,
    FsrsScheduler,
)
from core_api.domain.scheduling.rating import ReviewRating

# Below this many scored reviews (repeat reviews of a unit) the user keeps the defaults: 200 is
# enough for three parameters to be better than noise; py-fsrs advises ~1000 for all 21 (Coder).
MIN_SCORED_REVIEWS = 200
# A new version must beat the current parameters by this much mean log-loss per review (Coder).
MIN_IMPROVEMENT = 0.001
KEPT_VERSIONS = 5
ROUNDS = 2

_EPSILON = 1e-4
_INITIAL_STABILITY = range(0, 4)  # w0..w3: stability after the first review, by rating
_GROWTH = 8  # w8: how much a successful review grows stability
_DECAY = 20  # w20: shape of the forgetting curve
_INITIAL_FACTORS = (0.5, 0.7, 0.85, 1.2, 1.4, 2.0)
_GROWTH_STEPS = (-0.6, -0.3, -0.1, 0.1, 0.3, 0.6)
_DECAY_STEPS = (-0.06, -0.03, -0.01, 0.01, 0.03, 0.06)

Reviews = Sequence[tuple[ReviewRating, datetime]]  # one unit's reviews, oldest first


class NothingToRollBackError(Exception):
    """The user is on the defaults: there is no earlier version to go back to."""


@dataclass(frozen=True)
class Fit:
    parameters: tuple[float, ...]
    loss: float  # mean log-loss with the new parameters
    baseline_loss: float  # the same with the parameters the fit started from
    scored_reviews: int


def active_parameters(
    fsrs_params: Mapping[str, Any] | None, version: int | None
) -> tuple[float, ...] | None:
    """The parameters of the active version; None (the defaults) if there is none."""
    if version is None or not fsrs_params:
        return None
    for entry in fsrs_params.get("versions", ()):
        if entry["version"] == version:
            return tuple(float(value) for value in entry["parameters"])
    return None


def add_version(
    fsrs_params: Mapping[str, Any] | None,
    parameters: Sequence[float],
    *,
    scored_reviews: int,
    loss: float,
    at: datetime,
) -> tuple[dict[str, Any], int]:
    """The history with a new version appended (the oldest dropped past `KEPT_VERSIONS`), and
    the new version's number, which is above every number used so far."""
    versions = list((fsrs_params or {}).get("versions", ()))
    number = max((entry["version"] for entry in versions), default=0) + 1
    versions.append(
        {
            "version": number,
            "parameters": [float(value) for value in parameters],
            "scored_reviews": scored_reviews,
            "loss": loss,
            "fitted_at": at.astimezone(UTC).isoformat(),
        }
    )
    return {"versions": versions[-KEPT_VERSIONS:]}, number


def previous_version(fsrs_params: Mapping[str, Any] | None, version: int | None) -> int | None:
    """The version before `version` in the history, or None (the defaults) if it was the first
    kept. Raises `NothingToRollBackError` when `version` is already None."""
    if version is None:
        raise NothingToRollBackError
    earlier = [
        entry["version"]
        for entry in (fsrs_params or {}).get("versions", ())
        if entry["version"] < version
    ]
    return max(earlier, default=None)


def fit_parameters(
    units: Sequence[Reviews], start: Sequence[float] = DEFAULT_PARAMETERS
) -> Fit | None:
    """Fit parameters to `units`, starting from `start`; None if there are too few repeat
    reviews to score or no candidate beats `start` by `MIN_IMPROVEMENT`."""
    scored = sum(max(len(unit) - 1, 0) for unit in units)
    if scored < MIN_SCORED_REVIEWS:
        return None
    best = tuple(start)
    baseline = _mean_loss(units, best, scored)
    best_loss = baseline
    for _ in range(ROUNDS):
        for candidate in _candidates(best):
            loss = _mean_loss(units, candidate, scored)
            if loss < best_loss:
                best, best_loss = candidate, loss
    if baseline - best_loss < MIN_IMPROVEMENT:
        return None
    return Fit(parameters=best, loss=best_loss, baseline_loss=baseline, scored_reviews=scored)


def _candidates(base: tuple[float, ...]) -> list[tuple[float, ...]]:
    candidates: list[tuple[float, ...]] = []
    for factor in _INITIAL_FACTORS:
        values = list(base)
        for index in _INITIAL_STABILITY:
            values[index] = _clamp(index, values[index] * factor)
        candidates.append(tuple(values))
    for index, steps in ((_GROWTH, _GROWTH_STEPS), (_DECAY, _DECAY_STEPS)):
        for step in steps:
            values = list(base)
            values[index] = _clamp(index, values[index] + step)
            candidates.append(tuple(values))
    return candidates


def _clamp(index: int, value: float) -> float:
    return min(max(value, LOWER_BOUNDS_PARAMETERS[index]), UPPER_BOUNDS_PARAMETERS[index])


def _mean_loss(units: Sequence[Reviews], parameters: Sequence[float], scored: int) -> float:
    scheduler = FsrsScheduler(parameters)
    total = 0.0
    for reviews in units:
        state = None
        for rating, reviewed_at in reviews:
            if state is not None:
                predicted = scheduler.retrievability(state, reviewed_at)
                predicted = min(max(predicted, _EPSILON), 1 - _EPSILON)
                recalled = rating != ReviewRating.AGAIN
                total -= math.log(predicted if recalled else 1 - predicted)
            state = scheduler.review(state, rating, reviewed_at)
    return total / scored
