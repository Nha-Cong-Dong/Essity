"""T8.5 plan commit 2: `TodayRepository.practice_candidates` (US-06 AC8). Red when a not-ready,
retired, other-user's or deleted-subject question is a candidate, or the state is not read."""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import Subject
from core_api.repositories.today import TodayRepository
from practice_bench import Bench, schedule
from v2_rows import make_type


def bench_of(client: TestClient, db_session: Session) -> Bench:
    user, _ = signed_in(db_session)
    return Bench(db_session, user)


def test_ready_questions_with_and_without_state(client: TestClient, db_session: Session) -> None:
    bench = bench_of(client, db_session)
    kind = make_type(db_session, bench.user, bench.subject, ref_time_s=240)
    fresh = bench.ready()
    done = bench.ready(type_id=kind.id)
    schedule(db_session, bench.user, done, FROZEN_NOW)
    rows = {
        c.question_id: c for c in TodayRepository(db_session, bench.user.id).practice_candidates()
    }
    assert set(rows) == {fresh.id, done.id}
    assert rows[fresh.id].state is None and rows[fresh.id].removed is False
    assert rows[done.id].state is not None and rows[done.id].ref_time_s == 240.0
    assert rows[fresh.id].ref_time_s > 0


def test_not_ready_retired_review_and_removed_flags(
    client: TestClient, db_session: Session
) -> None:
    bench = bench_of(client, db_session)
    later = bench.section("UDP", studied=False)
    bench.card(later)
    waiting = bench.question(later)
    loose = bench.question()
    retired = bench.ready(status="retired")
    review_q = bench.ready(source="review_auto", run_id=uuid.uuid4())  # not practice
    gone = bench.ready()
    schedule(db_session, bench.user, gone, FROZEN_NOW, removed=FROZEN_NOW)
    got = TodayRepository(db_session, bench.user.id).practice_candidates()
    assert {c.question_id for c in got} == {gone.id}
    assert next(iter(got)).removed is True
    assert not {c.question_id for c in got} & {waiting.id, loose.id, retired.id, review_q.id}


def test_other_users_and_deleted_subjects_are_hidden(
    client: TestClient, db_session: Session
) -> None:
    mine = bench_of(client, db_session)
    mine.ready()
    other_user, _ = signed_in(db_session)
    theirs = Bench(db_session, other_user)
    theirs.ready()
    got = TodayRepository(db_session, mine.user.id).practice_candidates()
    assert len(got) == 1
    subject = db_session.get(Subject, mine.subject.id)
    assert subject is not None
    subject.deleted_at = FROZEN_NOW - timedelta(days=1)
    db_session.flush()
    assert TodayRepository(db_session, mine.user.id).practice_candidates() == []
