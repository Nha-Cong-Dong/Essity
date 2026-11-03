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
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.db.models import Attempt, Question, User
from core_api.db.models import PracticeState as PracticeStateRow
from core_api.domain.explain import Reason, explain
from core_api.domain.learning_day import day_bounds, learning_day
from core_api.domain.practice_mix import (
    MixItem,
    PracticeQuestion,
    card_seconds,
    mix,
    practice_seconds,
    split_practice,
)
from core_api.domain.scheduling.fsrs_adapter import MemoryState, Phase
from core_api.domain.today import DueUnit, PlannedQuestion, TodayPlan, compose_today, exam_weight
from core_api.domain.today_v2 import TodayInputs, TodayV2, compose, review_from_plan
from core_api.jobs.regenerate_review_question import enqueue_review_question
from core_api.repositories.review import (
    ReviewSessionItemRepository,
    ReviewSessionRepository,
    SessionStep,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.today import CARD_SOURCE, PracticeCandidate, TodayRepository
from core_api.repositories.user_scheduler import scheduler_for, scheduler_for_id
from core_api.services.suggestions import subject_inputs

_log = logging.getLogger("core_api.today")
NEW_CARD_RISK = 0.5  # a card never asked: between a fresh and a nearly forgotten one


@dataclass(frozen=True)
class MixedEntry:
    """One question of Ôn hôm nay: a card's review question or a due practice question."""

    question_id: uuid.UUID
    subject_id: uuid.UUID
    kind: Literal["card", "practice"]
    risk: float  # higher = more likely forgotten
    retrievability: float | None  # None: a card never asked
    days_since_last: int | None


@dataclass(frozen=True)
class MixedReview:
    """What Today shows and what a review session starts with (the one chooser, T7.11 D1).
    `plan`: the card part (items are cards only; backlog is the cards'); `entries`: every item in
    the order of the session; `fresh`: ready practice questions never attempted (Luyện tập)."""

    plan: TodayPlan
    entries: list[MixedEntry]
    minutes: int
    next_day: date | None  # only when nothing is due today: the next day a card or question is due
    units: Sequence[DueUnit]
    exams: dict[uuid.UUID, date]
    fresh: list[PracticeCandidate]
    names: dict[uuid.UUID, str]


def _seconds_of(candidate: PracticeCandidate) -> float:
    return practice_seconds(candidate.ref_time_s)


def compose_mixed(
    session: Session,
    user: User,
    now: datetime,
    reads: TodayRepository,
    *,
    subject_id: uuid.UUID | None = None,
) -> MixedReview:
    """The cards due and the practice questions due in one list under the shared cap (US-03 AC4):
    riskiest first whatever the kind, each kind keeping `KIND_FLOOR` places when both are due.
    Two passes: the v1 composer picks the cards (it keeps the new-card floor and the exam quota,
    T2.23); the mix then shares the cap, and when it cuts cards the composer picks again for the
    places left. Without a due practice question the answer is the v1 plan, unchanged."""
    scheduler = scheduler_for(user)
    tz = ZoneInfo(user.timezone)
    day = learning_day(now, tz, user.day_start_hour)
    listed = SubjectRepository(session, user.id).list_with_exams()
    exams = {subject.id: exam.exam_date for subject, exam, _ in listed}
    names = {subject.id: subject.name for subject, _, _ in listed}
    units = [u for u in reads.scheduled_units() if subject_id in (None, u.subject_id)]
    new_cards = [q for q in reads.new_questions(day=day) if subject_id in (None, q.subject_id)]
    unasked = {
        s: n for s, n in reads.unasked_by_subject(day=day).items() if subject_id in (None, s)
    }

    def pick_cards(room: int | None = None) -> TodayPlan:
        return compose_today(
            units,
            new_cards,
            exams,
            now=now,
            tz=tz,
            day_start_hour=user.day_start_hour,
            unasked=unasked,
            room=room,
            scheduler=scheduler,
        )

    plan = pick_cards()
    end_of_today = day_bounds(day, tz, user.day_start_hour)[1]
    candidates = [c for c in reads.practice_candidates() if subject_id in (None, c.subject_id)]
    by_id = {c.question_id: c for c in candidates}
    due_ids, fresh_ids = split_practice(
        PracticeQuestion(
            c.question_id,
            ready=True,
            scheduled=c.state is not None,
            due=c.state is not None and c.state.due < end_of_today,
            removed=c.removed,
        )
        for c in candidates
    )
    fresh = [by_id[i] for i in fresh_ids]
    states: dict[uuid.UUID, list[MemoryState]] = defaultdict(list)
    for unit in units:
        states[unit.question_id].append(unit.state)

    def card_entry(item: PlannedQuestion) -> MixedEntry:
        held = states.get(item.question_id, [])
        if item.kind == "new" or not held:
            return MixedEntry(item.question_id, item.subject_id, "card", NEW_CARD_RISK, None, None)
        recall = min(scheduler.retrievability(st, now) for st in held)
        weight = exam_weight(exams.get(item.subject_id), day)
        reason = explain(held, now, scheduler)
        return MixedEntry(
            item.question_id,
            item.subject_id,
            "card",
            1 - recall * weight,
            reason.retrievability,
            reason.days_since_last,
        )

    due_entries: list[MixedEntry] = []
    for question_id in due_ids:
        c = by_id[question_id]
        assert c.state is not None
        recall = scheduler.retrievability(c.state, now)
        weight = exam_weight(exams.get(c.subject_id), day)
        last = c.state.last_review
        days = max(0, (now - last).days)
        due_entries.append(
            MixedEntry(question_id, c.subject_id, "practice", 1 - recall * weight, recall, days)
        )

    if not due_entries:
        entries = [card_entry(i) for i in plan.items]
        next_day = plan.next_day
        if not entries:
            later: list[date] = [
                learning_day(c.state.due, tz, user.day_start_hour)
                for c in candidates
                if c.state is not None and not c.removed
            ]
            if plan.next_day is not None:
                later.append(plan.next_day)
            next_day = min(later) if later else None
        return MixedReview(plan, entries, plan.minutes, next_day, units, exams, fresh, names)

    card_entries = {e.question_id: e for e in map(card_entry, plan.items)}
    items = [MixItem(e.question_id, "card", e.risk, card_seconds()) for e in card_entries.values()]
    items += [
        MixItem(
            e.question_id, "practice", e.risk, practice_seconds(by_id[e.question_id].ref_time_s)
        )
        for e in due_entries
    ]
    kept = {i.item_id for i in mix(items).items}
    kept_cards = sum(1 for question_id in card_entries if question_id in kept)
    if kept_cards < len(plan.items):
        plan = pick_cards(room=kept_cards)
        card_entries = {e.question_id: e for e in map(card_entry, plan.items)}
    entries = sorted(
        [*card_entries.values(), *(e for e in due_entries if e.question_id in kept)],
        key=lambda e: (-e.risk, e.kind != "card", e.question_id),
    )
    seconds = sum(
        card_seconds() if e.kind == "card" else _seconds_of(by_id[e.question_id]) for e in entries
    )
    return MixedReview(plan, entries, -int(-seconds // 60), None, units, exams, fresh, names)


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
    scheduler = scheduler_for(user)
    tz = ZoneInfo(user.timezone)
    day = learning_day(now, tz, user.day_start_hour)
    states: dict[uuid.UUID, list[MemoryState]] = defaultdict(list)
    for unit in units:
        states[unit.question_id].append(unit.state)
    reasons: dict[uuid.UUID, Reason] = {
        item.question_id: explain(states.get(item.question_id, []), now, scheduler)
        for item in plan.items
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


def is_practice(question: Question) -> bool:
    """Bank and generated questions are practice; only a review question is a card."""
    return question.source != CARD_SOURCE


def session_steps(
    session: Session, user_id: uuid.UUID, review_session_id: uuid.UUID
) -> list[SessionStep]:
    """The one reader of a session's steps (T8.5): `progress` plus the practice steps. A practice
    question is answered by a practice attempt (no session, `/v1/practice`) submitted after the
    session began; one taken out of practice can no longer be asked. Every route that counts or
    shows steps comes through here, so position, total and "done" agree."""
    items = ReviewSessionItemRepository(session, user_id)
    steps = items.progress(review_session_id)
    practice_ids = [s.question.id for s in steps if is_practice(s.question)]
    if not practice_ids:
        return steps
    found = ReviewSessionRepository(session, user_id).get(review_session_id)
    if found is None:
        return steps
    answered: dict[uuid.UUID, Attempt] = {}
    for attempt in session.scalars(
        select(Attempt)
        .where(
            Attempt.user_id == user_id,
            Attempt.review_session_id.is_(None),
            Attempt.status == "submitted",
            Attempt.question_id.in_(practice_ids),
            Attempt.submitted_at >= found.started_at,
        )
        .order_by(Attempt.submitted_at, Attempt.id)
    ):
        answered[attempt.question_id] = attempt
    closed = set(
        session.scalars(
            select(PracticeStateRow.question_id).where(
                PracticeStateRow.user_id == user_id,
                PracticeStateRow.question_id.in_(practice_ids),
                PracticeStateRow.removed_at.is_not(None),
            )
        )
    )
    return items.progress(review_session_id, practice_attempts=answered, closed=closed)


def practice_reason(
    session: Session, user_id: uuid.UUID, question_id: uuid.UUID, now: datetime
) -> Reason:
    """Why a practice question comes up: the recall chance of its own schedule, never a card's."""
    row = session.scalars(
        select(PracticeStateRow).where(
            PracticeStateRow.user_id == user_id, PracticeStateRow.question_id == question_id
        )
    ).one_or_none()
    if row is None:
        return Reason(kind="new", retrievability=None, days_since_last=None)
    state = MemoryState(
        phase=Phase(row.phase),
        step=row.step,
        stability=row.stability,
        difficulty=row.difficulty,
        due=row.due,
        last_review=row.last_review,
    )
    return Reason(
        kind="review",
        retrievability=scheduler_for_id(session, user_id).retrievability(state, now),
        days_since_last=max(0, (now - row.last_review).days),
    )
