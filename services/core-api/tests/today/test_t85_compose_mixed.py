"""T8.5 (US-03 AC4, US-06 AC8, US-16 AC1; plan commit 3): `compose_mixed`, the one chooser of Ôn
hôm nay. Cards and due practice questions share one cap; a due practice question is in Ôn only,
a never-attempted one in Luyện tập only."""

import uuid
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from test_t28_today_api import Space

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import Question, User
from core_api.domain.learning_day import day_bounds, learning_day
from core_api.domain.practice_mix import KIND_FLOOR
from core_api.domain.today import MAX_MINUTES, MAX_QUESTIONS
from core_api.repositories.today import TodayRepository
from core_api.services.today import MixedReview, compose_mixed
from practice_bench import Bench, schedule
from v2_rows import make_type

OVERDUE = FROZEN_NOW - timedelta(days=30)


def mixed(session: Session, user: User, subject_id: uuid.UUID | None = None) -> MixedReview:
    reads = TodayRepository(session, user.id)
    return compose_mixed(session, user, FROZEN_NOW, reads, subject_id=subject_id)


def due_cards(space: Space, subject: uuid.UUID, n: int) -> None:
    for i in range(n):
        unit_id, _ = space.question(subject, f"card{i}")
        space.scheduled(unit_id, due_in_days=-1)


def due_practice(session: Session, bench: Bench, n: int, **kw: Any) -> list[Question]:
    out: list[Question] = []
    for _ in range(n):
        q = bench.ready(**kw)
        schedule(session, bench.user, q, OVERDUE + timedelta(days=29))
        out.append(q)
    return out


def user_of(session: Session) -> User:
    user, _ = signed_in(session)
    return user


def kinds(result: MixedReview) -> list[str]:
    return [e.kind for e in result.entries]


def test_shared_cap_20_items_30_minutes(db_session: Session) -> None:
    user = user_of(db_session)
    space = Space(db_session, user)
    due_cards(space, space.subject(), 40)
    due_practice(db_session, Bench(db_session, user), 40)
    result = mixed(db_session, user)
    assert len(result.entries) <= MAX_QUESTIONS
    assert result.minutes <= MAX_MINUTES
    assert {"card", "practice"} <= set(kinds(result))
    assert len({e.question_id for e in result.entries}) == len(result.entries)


def test_practice_question_uses_type_ref_time(db_session: Session) -> None:
    user = user_of(db_session)
    bench = Bench(db_session, user)
    kind = make_type(db_session, user, bench.subject, ref_time_s=600)
    due_practice(db_session, bench, 5, type_id=kind.id)
    result = mixed(db_session, user)
    assert len(result.entries) == 3  # 3 x 10 min = 30 min
    assert result.minutes == 30


def test_riskiest_first_kind_ignored(db_session: Session) -> None:
    user = user_of(db_session)
    space = Space(db_session, user)
    due_cards(space, space.subject(), 2)
    bench = Bench(db_session, user)
    risky = bench.ready()
    schedule(db_session, user, risky, OVERDUE)
    calm = bench.ready()
    schedule(
        db_session,
        user,
        calm,
        FROZEN_NOW - timedelta(hours=1),
        last_review=FROZEN_NOW - timedelta(days=1),
    )
    order = [e.question_id for e in mixed(db_session, user).entries]
    assert order[0] == risky.id  # more likely forgotten than every card
    assert order[-1] == calm.id  # less likely forgotten than every card


def test_floor_each_kind_when_both_due(db_session: Session) -> None:
    user = user_of(db_session)
    space = Space(db_session, user)
    due_cards(space, space.subject(), 25)
    bench = Bench(db_session, user)
    for q in [bench.ready() for _ in range(5)]:
        schedule(
            db_session,
            user,
            q,
            FROZEN_NOW - timedelta(hours=1),
            last_review=FROZEN_NOW - timedelta(hours=2),
        )
    result = mixed(db_session, user)
    assert kinds(result).count("practice") >= KIND_FLOOR
    assert kinds(result).count("card") >= KIND_FLOOR


def test_due_practice_only_in_review_never_in_practice_part(db_session: Session) -> None:
    user = user_of(db_session)
    bench = Bench(db_session, user)
    (due,) = due_practice(db_session, bench, 1)
    never = bench.ready()
    result = mixed(db_session, user)
    assert [e.question_id for e in result.entries] == [due.id]
    assert [c.question_id for c in result.fresh] == [never.id]


def test_first_attempt_moves_a_question_from_practice_to_review(db_session: Session) -> None:
    user = user_of(db_session)
    bench = Bench(db_session, user)
    q = bench.ready()
    assert [c.question_id for c in mixed(db_session, user).fresh] == [q.id]
    schedule(db_session, user, q, FROZEN_NOW - timedelta(days=1))
    after = mixed(db_session, user)
    assert after.fresh == [] and [e.question_id for e in after.entries] == [q.id]


def test_removed_or_not_ready_in_neither_place(db_session: Session) -> None:
    user = user_of(db_session)
    bench = Bench(db_session, user)
    gone = bench.ready()
    schedule(db_session, user, gone, OVERDUE, removed=FROZEN_NOW)
    bench.question()  # unlinked: not ready
    result = mixed(db_session, user)
    assert result.entries == [] and result.fresh == []


def test_new_card_floor_survives_practice_cut(db_session: Session) -> None:
    user = user_of(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    due_cards(space, subject, 25)
    for i in range(6):
        space.question(subject, f"new{i}")
    due_practice(db_session, Bench(db_session, user), 12)
    result = mixed(db_session, user)
    new_cards = [e for e in result.entries if e.kind == "card" and e.retrievability is None]
    assert len(new_cards) >= 5  # NEW_FLOOR
    assert len(result.entries) <= MAX_QUESTIONS


def test_due_boundary_is_the_learning_day_end(db_session: Session) -> None:
    user = user_of(db_session)
    tz = ZoneInfo(user.timezone)
    end = day_bounds(learning_day(FROZEN_NOW, tz, user.day_start_hour), tz, user.day_start_hour)[1]
    bench = Bench(db_session, user)
    inside = bench.ready()
    schedule(db_session, user, inside, end - timedelta(minutes=1))
    outside = bench.ready()
    schedule(db_session, user, outside, end + timedelta(minutes=1))
    result = mixed(db_session, user)
    assert [e.question_id for e in result.entries] == [inside.id]
    assert result.fresh == []  # an attempted question is never "new"


def test_other_users_practice_never_shows(db_session: Session) -> None:
    mine, theirs = user_of(db_session), user_of(db_session)
    due_practice(db_session, Bench(db_session, theirs), 3)
    Bench(db_session, theirs).ready()
    result = mixed(db_session, mine)
    assert result.entries == [] and result.fresh == []


def test_subject_filter_applies_to_practice(db_session: Session) -> None:
    user = user_of(db_session)
    a = Bench(db_session, user)
    b = Bench(db_session, user)
    (qa,) = due_practice(db_session, a, 1)
    due_practice(db_session, b, 1)
    result = mixed(db_session, user, subject_id=a.subject.id)
    assert [e.question_id for e in result.entries] == [qa.id]


def test_practice_only_day_has_items_and_no_next_day(db_session: Session) -> None:
    user = user_of(db_session)
    due_practice(db_session, Bench(db_session, user), 2)
    result = mixed(db_session, user)
    assert len(result.entries) == 2 and result.next_day is None and result.minutes > 0


def test_next_day_counts_practice_schedule(db_session: Session) -> None:
    user = user_of(db_session)
    q = Bench(db_session, user).ready()
    schedule(db_session, user, q, FROZEN_NOW + timedelta(days=3))
    result = mixed(db_session, user)
    assert result.entries == [] and result.next_day is not None
