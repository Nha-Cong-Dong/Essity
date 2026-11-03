# pyright: reportPrivateUsage=false
"""T5.9b (review #163 F1): every retrievability the app shows or ranks by uses the user's ACTIVE
FSRS parameters, the curve that set the due dates; a user without a fitted version gets exactly
the numbers they had before. One test per call site."""

import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session
from test_t28_today_api import Space

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import User
from core_api.domain.explain import explain
from core_api.domain.scheduling.fsrs_adapter import (
    DEFAULT_PARAMETERS,
    FsrsScheduler,
    MemoryState,
    Phase,
)
from core_api.domain.scheduling.practice import PracticeState, is_known
from core_api.domain.today import compose_today
from core_api.repositories.progress import ProgressRepository
from core_api.repositories.review import MemoryStateRepository
from core_api.repositories.stats import StatsRepository
from core_api.repositories.today import TodayRepository
from core_api.services.today import build_v2, compose_mixed, practice_reason
from practice_bench import Bench, schedule

FITTED = [*DEFAULT_PARAMETERS[:20], 0.5]  # w20, the shape of the curve, moved
FITTED_SCHEDULER = FsrsScheduler(FITTED)
DEFAULT_SCHEDULER = FsrsScheduler()
STATE = MemoryState(
    phase=Phase.REVIEW,
    step=None,
    stability=10.0,
    difficulty=5.0,
    due=FROZEN_NOW + timedelta(days=1),
    last_review=FROZEN_NOW - timedelta(days=30),  # at 10 days both curves give 0.9
)
FITTED_RECALL = FITTED_SCHEDULER.retrievability(STATE, FROZEN_NOW)
DEFAULT_RECALL = DEFAULT_SCHEDULER.retrievability(STATE, FROZEN_NOW)


def fit(user: User, session: Session) -> None:
    user.fsrs_params = {"versions": [{"version": 1, "parameters": FITTED}]}
    user.fsrs_params_version = 1
    session.flush()


def stale(space: Space, unit_id: uuid.UUID, stability: float = 10.0) -> None:
    """A core schedule overdue since yesterday, last reviewed 30 days ago."""
    state = replace(STATE, stability=stability, due=FROZEN_NOW - timedelta(days=1))
    MemoryStateRepository(space.session, space.user.id).upsert(unit_id, "core", state)
    space.session.flush()


def test_the_two_curves_differ() -> None:
    assert abs(FITTED_RECALL - DEFAULT_RECALL) > 1e-3


def test_explain_uses_the_given_scheduler() -> None:
    assert explain([STATE], FROZEN_NOW).retrievability == DEFAULT_RECALL
    assert explain([STATE], FROZEN_NOW, FITTED_SCHEDULER).retrievability == FITTED_RECALL


def test_is_known_uses_the_given_scheduler() -> None:
    state = PracticeState(memory=STATE, last_verdict="correct", removed_at=None)
    assert is_known(state, FROZEN_NOW) is (DEFAULT_RECALL >= 0.9)
    assert is_known(state, FROZEN_NOW, scheduler=FITTED_SCHEDULER) is (FITTED_RECALL >= 0.9)


def test_compose_today_ranks_by_the_given_scheduler(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    first, _ = space.question(space.subject(), "weak")
    second, _ = space.question(space.subject("Toán"), "strong")
    stale(space, first)
    stale(space, second, stability=100.0)
    units = TodayRepository(db_session, user.id).scheduled_units()

    class Reversed(FsrsScheduler):
        def retrievability(self, state: MemoryState, at: datetime) -> float:
            return -super().retrievability(state, at)

    def order(scheduler: FsrsScheduler | None) -> list[object]:
        extra = {} if scheduler is None else {"scheduler": scheduler}
        plan = compose_today(
            units,
            [],
            {},
            now=FROZEN_NOW,
            tz=ZoneInfo(user.timezone),
            day_start_hour=user.day_start_hour,
            **extra,  # type: ignore[arg-type]
        )
        return [i.question_id for i in plan.items]

    assert len(order(None)) == 2
    assert order(Reversed()) == list(reversed(order(None)))


def test_compose_mixed_card_and_practice_entries_use_the_users_params(
    db_session: Session,
) -> None:
    user, _ = signed_in(db_session)
    fit(user, db_session)
    space = Space(db_session, user)
    unit_id, question = space.question(space.subject(), "card")
    question_id = question.id
    stale(space, unit_id)
    practice = Bench(db_session, user).ready()
    schedule(
        db_session, user, practice, FROZEN_NOW - timedelta(days=1), last_review=STATE.last_review
    )
    result = compose_mixed(db_session, user, FROZEN_NOW, TodayRepository(db_session, user.id))
    by_id = {e.question_id: e for e in result.entries}
    assert by_id[question_id].retrievability == pytest.approx(FITTED_RECALL)
    assert by_id[practice.id].retrievability == pytest.approx(FITTED_RECALL)


def test_compose_mixed_without_fitted_params_is_unchanged(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    unit_id, question = space.question(space.subject(), "card")
    question_id = question.id
    stale(space, unit_id)
    result = compose_mixed(db_session, user, FROZEN_NOW, TodayRepository(db_session, user.id))
    entry = next(e for e in result.entries if e.question_id == question_id)
    assert entry.retrievability == DEFAULT_RECALL


def test_build_v2_reason_uses_the_users_params(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    fit(user, db_session)
    space = Space(db_session, user)
    unit_id, question = space.question(space.subject(), "card")
    question_id = question.id
    stale(space, unit_id)
    reads = TodayRepository(db_session, user.id)
    mixed = compose_mixed(db_session, user, FROZEN_NOW, reads)
    parts = build_v2(db_session, user, FROZEN_NOW, mixed.plan, mixed.units, reads)
    found = [r for r in parts.review.items if r.question_id == question_id]
    assert [r.retrievability for r in found] == [pytest.approx(FITTED_RECALL)]


def test_practice_reason_uses_the_users_params(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    question = Bench(db_session, user).ready()
    schedule(
        db_session, user, question, FROZEN_NOW + timedelta(days=1), last_review=STATE.last_review
    )
    assert practice_reason(db_session, user.id, question.id, FROZEN_NOW).retrievability == (
        DEFAULT_RECALL
    )
    fit(user, db_session)
    assert practice_reason(
        db_session, user.id, question.id, FROZEN_NOW
    ).retrievability == pytest.approx(FITTED_RECALL)


def test_progress_units_use_the_users_params(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    unit_id, _ = space.question(space.subject(), "card")
    stale(space, unit_id)
    repo = ProgressRepository(db_session, user.id)

    def recalls() -> list[float | None]:
        return [u.recall for group in repo._units(FROZEN_NOW)[0].values() for u in group]

    assert recalls() == [DEFAULT_RECALL]
    fit(user, db_session)
    assert recalls() == [pytest.approx(FITTED_RECALL)]


def test_stats_retentions_use_the_users_params(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    unit_id, _ = space.question(space.subject(), "card")
    stale(space, unit_id)
    repo = StatsRepository(db_session, user.id)
    assert list(repo.retentions(FROZEN_NOW).values()) == [[DEFAULT_RECALL]]
    fit(user, db_session)
    assert list(repo.retentions(FROZEN_NOW).values()) == [[pytest.approx(FITTED_RECALL)]]


def test_stats_bank_uses_the_users_params(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    question = Bench(db_session, user).ready()
    schedule(
        db_session, user, question, FROZEN_NOW + timedelta(days=1), last_review=STATE.last_review
    )
    repo = StatsRepository(db_session, user.id)

    def recalls() -> list[float | None]:
        return [q.retrievability for group in repo.bank(FROZEN_NOW).values() for q in group]

    assert recalls() == [DEFAULT_RECALL]
    fit(user, db_session)
    assert recalls() == [pytest.approx(FITTED_RECALL)]
