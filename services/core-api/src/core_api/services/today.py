"""Today v2 (T7.11): the three parts around the v1 plan, and the lazy review-question hook.

The questions come from `compose_today` only (plan D1), the same chooser the review session
starts with, so what Today shows is what the session will ask. This module adds, around that plan:
why each question, what to study next (T7.10 suggestions), the unfinished work, and, for a card
whose question is older than its revision, a lazy job that writes the new question before the
card is asked (T7.9, US-02b AC11)."""

import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from core_api.db.models import User
from core_api.domain.explain import Reason, explain
from core_api.domain.learning_day import day_bounds, learning_day
from core_api.domain.scheduling.fsrs_adapter import MemoryState
from core_api.domain.today import DueUnit, TodayPlan
from core_api.domain.today_v2 import TodayInputs, TodayV2, compose, review_from_plan
from core_api.jobs.regenerate_review_question import enqueue_review_question
from core_api.repositories.today import TodayRepository
from core_api.services.suggestions import subject_inputs

_log = logging.getLogger("core_api.today")


def build_v2(
    session: Session,
    user: User,
    now: datetime,
    plan: TodayPlan,
    units: Sequence[DueUnit],
    reads: TodayRepository,
) -> TodayV2:
    """The v2 parts for this plan. `units`: every scheduled unit the plan was composed from; the
    reason of a due question is read from their schedules (no query per question)."""
    tz = ZoneInfo(user.timezone)
    day = learning_day(now, tz, user.day_start_hour)
    states: dict[uuid.UUID, list[MemoryState]] = defaultdict(list)
    for unit in units:
        states[unit.question_id].append(unit.state)
    reasons: dict[uuid.UUID, Reason] = {
        item.question_id: explain(states.get(item.question_id, []), now) for item in plan.items
    }
    review = review_from_plan(plan, reasons, new_saved_today=reads.saved_on(day))
    subjects, names = subject_inputs(session, user)
    inputs = TodayInputs(
        now=now,
        tz=tz,
        day_start_hour=user.day_start_hour,
        subjects=subjects,
        subject_names=names,
        cards=[],
        sessions=reads.unfinished_sessions(),
    )
    return compose(inputs, review=review)


def enqueue_lazy_questions(
    session: Session,
    user: User,
    now: datetime,
    reads: TodayRepository,
    question_ids: Sequence[uuid.UUID],
) -> int:
    """For each card of today's review whose newest revision is later than its question's, add
    the lazy job (at most one per card per learning day, whatever became of the last: a failed or
    empty one is not retried by every refetch of Today). Never fails the read: a queue error is
    logged (ids only) and the answer goes out without the job. Returns the jobs added."""
    stale = reads.stale_rev_units(question_ids)
    if not stale:
        return 0
    tz = ZoneInfo(user.timezone)
    day = learning_day(now, tz, user.day_start_hour)
    start = day_bounds(day, tz, user.day_start_hour)[0]
    blocked = reads.lazy_jobs_since(stale, start)
    todo = [unit for unit in stale if unit not in blocked]
    added = 0
    for unit_id in todo:
        try:
            with session.begin_nested():
                enqueue_review_question(session, user.id, unit_id, lazy=True)
            added += 1
        except Exception:  # noqa: BLE001 - a read must not fail for a background job
            _log.warning("lazy review question not enqueued", extra={"unit_id": str(unit_id)})
    return added
