"""The `optimize_fsrs` job (T5.9, ADR-0009): fit FSRS parameters to each user's own reviews.

Weekly. For each user with enough repeat reviews (`MIN_SCORED_REVIEWS`), fit parameters from
their review history; if they beat the current ones, store them as a new version and rebuild the
user's schedule from review_log with them. Users with too little history keep the defaults.
`rollback_fsrs_params` goes back to the previous version (or the defaults) and rebuilds.

Running twice is harmless: the second fit starts from the version the first stored and finds
nothing to improve. A user's failure is logged and does not stop the others.
"""

import logging
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from itertools import groupby
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.db.engine import get_engine
from core_api.db.models import User
from core_api.domain.scheduling.fsrs_adapter import DEFAULT_PARAMETERS
from core_api.domain.scheduling.params import (
    MIN_SCORED_REVIEWS,
    active_parameters,
    add_version,
    fit_parameters,
    previous_version,
)
from core_api.domain.scheduling.rating import ReviewRating
from core_api.jobs.handler import periodic_job
from core_api.repositories.practice import PracticeStateRepository
from core_api.repositories.review import MemoryStateRepository

OPTIMIZE_FSRS = "optimize_fsrs"

_log = logging.getLogger("core_api.jobs")


class Outcome(StrEnum):
    NEW_VERSION = "new_version"
    NOT_ENOUGH_HISTORY = "not_enough_history"
    NO_IMPROVEMENT = "no_improvement"


def optimize_user(session: Session, user_id: uuid.UUID, now: datetime) -> Outcome:
    """Fit and store parameters for one user; the schedule is rebuilt when a version is stored."""
    user = session.scalars(
        select(User).where(User.id == user_id).with_for_update(key_share=True)
    ).one()
    states = MemoryStateRepository(session, user_id)
    units = [
        [(ReviewRating(row[2]), row[3]) for row in reviews]
        for _, reviews in groupby(states.current_reviews(None), key=lambda row: (row[0], row[1]))
    ]
    if sum(max(len(unit) - 1, 0) for unit in units) < MIN_SCORED_REVIEWS:
        return Outcome.NOT_ENOUGH_HISTORY
    start = active_parameters(user.fsrs_params, user.fsrs_params_version) or DEFAULT_PARAMETERS
    fit = fit_parameters(units, start)
    if fit is None:
        return Outcome.NO_IMPROVEMENT
    history, version = add_version(
        user.fsrs_params,
        fit.parameters,
        scored_reviews=fit.scored_reviews,
        loss=fit.loss,
        at=now,
    )
    user.fsrs_params = history
    user.fsrs_params_version = version
    session.flush()
    states.rebuild()
    PracticeStateRepository(session, user_id).rebuild()
    return Outcome.NEW_VERSION


def rollback_fsrs_params(session: Session, user_id: uuid.UUID) -> int | None:
    """Make the previous version active (None: the defaults) and rebuild the user's schedule.
    Raises `NothingToRollBackError` if the user is on the defaults already."""
    user = session.scalars(
        select(User).where(User.id == user_id).with_for_update(key_share=True)
    ).one()
    user.fsrs_params_version = previous_version(user.fsrs_params, user.fsrs_params_version)
    session.flush()
    MemoryStateRepository(session, user_id).rebuild()
    PracticeStateRepository(session, user_id).rebuild()
    return user.fsrs_params_version


@periodic_job(OPTIMIZE_FSRS, cron="0 3 * * 0")
def optimize_fsrs_job(payload: dict[str, Any]) -> None:
    counts: dict[str, int] = {}
    with Session(get_engine()) as listing:
        user_ids = list(listing.scalars(select(User.id).where(User.deleted_at.is_(None))))
    for user_id in user_ids:
        try:
            with Session(get_engine()) as session:
                outcome = optimize_user(session, user_id, datetime.now(UTC))
                session.commit()
        except Exception:
            _log.exception("fsrs optimization failed", extra={"user_id": str(user_id)})
            counts["failed"] = counts.get("failed", 0) + 1
            continue
        counts[outcome.value] = counts.get(outcome.value, 0) + 1
    _log.info("fsrs parameters optimized", extra={"counts": counts})
