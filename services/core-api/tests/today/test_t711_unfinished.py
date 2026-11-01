"""T7.11 C3: unfinished work and stale review questions as the repository reads them.

US-03 AC1 (unfinished line), US-02b AC11 (lazy question), isolation (ADR-0013/14)."""

import itertools
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import Submission, UnitRevision
from core_api.repositories.question import QuestionUnitRepository
from core_api.repositories.today import TodayRepository
from v2_rows import make_question, make_study_session, make_subject, make_unit


def _submission(db: Session, user_id: object, session_id: object, status: str) -> None:
    finished = datetime.now(UTC) if status in ("done", "failed") else None
    db.add(Submission(user_id=user_id, session_id=session_id, status=status, finished_at=finished))
    db.flush()


def test_us03_ac1_unfinished_lists_draft_cards_and_pending_ai_submissions(
    db_session: Session,
) -> None:
    alice, _ = signed_in(db_session)
    subject = make_subject(db_session, alice)
    drafts = make_study_session(db_session, alice, subject)
    make_unit(db_session, alice, subject, status="draft", session_id=drafts.id)
    make_unit(db_session, alice, subject, status="draft", session_id=drafts.id)
    waiting = make_study_session(db_session, alice, subject)
    _submission(db_session, alice.id, waiting.id, "pending_ai")
    finished = make_study_session(db_session, alice, subject)
    _submission(db_session, alice.id, finished.id, "done")
    _submission(db_session, alice.id, make_study_session(db_session, alice, subject).id, "failed")
    make_study_session(db_session, alice, subject)  # nothing left in it

    rows = {r.session_id: r for r in TodayRepository(db_session, alice.id).unfinished_sessions()}
    assert set(rows) == {drafts.id, waiting.id}
    assert (rows[drafts.id].draft_cards, rows[drafts.id].pending_ai) == (2, False)
    assert (rows[waiting.id].draft_cards, rows[waiting.id].pending_ai) == (0, True)


def test_us03_ac1_unfinished_is_isolated_and_hides_deleted_subjects(db_session: Session) -> None:
    alice, _ = signed_in(db_session)
    bob, _ = signed_in(db_session)
    theirs = make_subject(db_session, bob)
    s = make_study_session(db_session, bob, theirs)
    make_unit(db_session, bob, theirs, status="draft", session_id=s.id)
    _submission(db_session, bob.id, s.id, "pending_ai")
    mine = make_subject(db_session, alice)
    gone = make_study_session(db_session, alice, mine)
    make_unit(db_session, alice, mine, status="draft", session_id=gone.id)
    mine.deleted_at = datetime.now(UTC)
    db_session.flush()
    assert TodayRepository(db_session, alice.id).unfinished_sessions() == []


_COUNTER = itertools.count(1)


def _card_with_question(db: Session, user: object, subject: object, rev_of_question: int | None):
    unit = make_unit(db, user, subject, status="canonical")  # type: ignore[arg-type]
    question = make_question(
        db,
        user,  # type: ignore[arg-type]
        subject,  # type: ignore[arg-type]
        n=next(_COUNTER),
        source="review_auto",
        unit_rev=rev_of_question,
    )
    QuestionUnitRepository(db, user.id).link(question.id, unit.id)  # type: ignore[attr-defined]
    return unit, question


def test_us02b_ac11_stale_rev_units_are_those_with_a_newer_revision_than_their_question(
    db_session: Session,
) -> None:
    alice, _ = signed_in(db_session)
    subject = make_subject(db_session, alice)
    stale, q_stale = _card_with_question(db_session, alice, subject, 1)
    fresh, q_fresh = _card_with_question(db_session, alice, subject, 2)
    legacy, q_legacy = _card_with_question(db_session, alice, subject, None)  # counts as rev 0
    for unit, revs in ((stale, (0, 1, 2)), (fresh, (0, 1, 2)), (legacy, (0, 1))):
        for rev in revs:
            db_session.add(
                UnitRevision(user_id=alice.id, unit_id=unit.id, rev=rev, origin="ai", content={})
            )
    db_session.flush()
    reads = TodayRepository(db_session, alice.id)
    got = reads.stale_rev_units([q_stale.id, q_fresh.id, q_legacy.id])
    assert set(got) == {stale.id, legacy.id}
    assert reads.stale_rev_units([]) == []


def test_us02b_ac11_a_card_without_revision_or_not_canonical_is_never_stale(
    db_session: Session,
) -> None:
    alice, _ = signed_in(db_session)
    subject = make_subject(db_session, alice)
    _no_rev, q1 = _card_with_question(db_session, alice, subject, 1)
    old, q2 = _card_with_question(db_session, alice, subject, 1)
    old.status = "active"
    db_session.add(UnitRevision(user_id=alice.id, unit_id=old.id, rev=3, origin="ai", content={}))
    db_session.flush()
    assert TodayRepository(db_session, alice.id).stale_rev_units([q1.id, q2.id]) == []


def test_us02b_ac11_stale_rev_is_isolated(db_session: Session) -> None:
    alice, _ = signed_in(db_session)
    bob, _ = signed_in(db_session)
    subject = make_subject(db_session, bob)
    unit, question = _card_with_question(db_session, bob, subject, 1)
    db_session.add(UnitRevision(user_id=bob.id, unit_id=unit.id, rev=2, origin="ai", content={}))
    db_session.flush()
    assert TodayRepository(db_session, alice.id).stale_rev_units([question.id]) == []
    assert TodayRepository(db_session, bob.id).stale_rev_units([question.id]) == [unit.id]


def _job(db: Session, user: object, unit: object, status: str, at: datetime) -> None:
    db.execute(
        text(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, args, status, scheduled_at)"
            " VALUES ('default', 'regenerate_review_question', CAST(:a AS jsonb), CAST(:s AS"
            " procrastinate_job_status), :at)"
        ),
        {"a": f'{{"user_id": "{user}", "unit_id": "{unit}", "lazy": true}}', "s": status, "at": at},
    )
    db.execute(
        text(
            "INSERT INTO procrastinate_events (job_id, type, at) SELECT max(id), 'deferred',"
            " :at FROM procrastinate_jobs"
        ),
        {"at": at},
    )


def test_us02b_ac11_a_lazy_job_blocks_another_for_the_card_until_the_next_learning_day(
    db_session: Session,
) -> None:
    alice, _ = signed_in(db_session)
    bob, _ = signed_in(db_session)
    subject = make_subject(db_session, alice)
    a, _qa = _card_with_question(db_session, alice, subject, 1)
    b, _qb = _card_with_question(db_session, alice, subject, 1)
    c, _qc = _card_with_question(db_session, alice, subject, 1)
    today_start = datetime(2026, 11, 2, 4, 0, tzinfo=UTC)
    after, before = datetime(2026, 11, 2, 9, 0, tzinfo=UTC), datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    _job(db_session, alice.id, a.id, "failed", after)  # ended, same day: still blocks
    _job(db_session, alice.id, b.id, "todo", before)  # waiting from yesterday: blocks
    _job(db_session, bob.id, c.id, "failed", after)  # someone else's job: does not
    _job(db_session, alice.id, c.id, "succeeded", before)  # ended yesterday: does not
    db_session.flush()
    got = TodayRepository(db_session, alice.id).lazy_jobs_since([a.id, b.id, c.id], today_start)
    assert got == {a.id, b.id}
