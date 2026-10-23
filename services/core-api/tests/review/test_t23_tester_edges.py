"""Edge cases the tester found missing for T2.1 + T2.3 (branch t2.1-t2.3-units-review-history).

Each test says which change in the code turns it red.
"""

import hashlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_t23_review_history import DAY, NOW, RUN, History, refused, refused_by_trigger

from clock import future_exam
from core_api.db.models import User
from core_api.domain.question_hash import content_hash
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler
from core_api.domain.scheduling.rating import ReviewRating, Verdict
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import (
    AttemptRepository,
    GradeRepository,
    MemoryStateRepository,
    ReviewSessionRepository,
    UnitsMismatchError,
)
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository


def test_tester_unit_with_history_can_still_change_status(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Retiring/splitting a reviewed unit is the way to "remove" it (plan D10). Red when: a
    # trigger or a stricter FK on knowledge_unit/question blocks UPDATE of a row with history.
    h = History(db_session, two_users[0])
    for status in ("split", "merged", "retired", "active"):
        db_session.execute(
            text("UPDATE knowledge_unit SET status = :s WHERE id = :id"),
            {"s": status, "id": h.unit.id},
        )
    db_session.execute(
        text("UPDATE question SET status = 'retired' WHERE id = :id"), {"id": h.question.id}
    )
    db_session.execute(
        text("UPDATE knowledge_unit SET title = 'TCP (sửa)', summary = 'mới' WHERE id = :id"),
        {"id": h.unit.id},
    )
    db_session.flush()
    kept = db_session.execute(
        text("SELECT count(*) FROM review_log WHERE user_id = :u"), {"u": h.user.id}
    ).scalar_one()
    assert kept == 1
    refused(db_session, "UPDATE knowledge_unit SET status = 'deleted' WHERE id = :id", id=h.unit.id)
    refused(db_session, "UPDATE question SET status = 'split' WHERE id = :id", id=h.question.id)


def test_tester_delete_all_memory_state_leaves_other_users_alone(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: `delete_all` drops the `user_id` filter (it would wipe Bob's cache too).
    alice, bob = two_users
    ha, hb = History(db_session, alice), History(db_session, bob)
    state = FsrsScheduler().review(None, ReviewRating.GOOD, NOW)
    MemoryStateRepository(db_session, alice.id).upsert(ha.unit.id, "core", state)
    MemoryStateRepository(db_session, bob.id).upsert(hb.unit.id, "core", state)
    db_session.flush()
    assert MemoryStateRepository(db_session, alice.id).delete_all() == 1
    db_session.flush()
    assert MemoryStateRepository(db_session, alice.id).state(ha.unit.id) is None
    assert MemoryStateRepository(db_session, bob.id).state(hb.unit.id) == state
    assert MemoryStateRepository(db_session, alice.id).delete_all() == 0  # empty: nothing, no error


def test_tester_add_idempotent_refuses_a_soft_deleted_subject(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: the subject check in `add_idempotent` goes (the FK would still accept the
    # soft-deleted row, so a seed would silently fill a subject the user has deleted).
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    subject, _ = subjects.create_with_exam("Cũ", future_exam())
    questions = QuestionRepository(db_session, alice.id)
    existing = questions.add_idempotent(
        subject.id, level=1, prompt="Q?", reference_answer="A", run_id=RUN
    )
    assert subjects.soft_delete(subject.id)
    db_session.flush()
    with pytest.raises(SubjectNotFoundError):
        questions.add_idempotent(subject.id, level=1, prompt="Q?", reference_answer="A", run_id=RUN)
    with pytest.raises(SubjectNotFoundError):
        questions.add_idempotent(
            subject.id, level=1, prompt="Khác", reference_answer="A", run_id=RUN
        )
    # The row it had is kept for good: soft delete never removes a question.
    count = db_session.execute(
        text("SELECT count(*) FROM question WHERE id = :id"), {"id": existing.id}
    ).scalar_one()
    assert count == 1


def test_tester_subject_with_history_cannot_be_hard_deleted(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Cascade from `subject` reaches knowledge_unit/question; tier 3 hangs on them with NO ACTION
    # (D10) or behind triggers (D1). Red when: a tier-3 FK to tier 2 becomes CASCADE and the
    # triggers go too, so deleting a subject quietly takes the review history with it.
    h = History(db_session, two_users[0])
    refused(db_session, "DELETE FROM subject WHERE id = :id", id=h.unit.subject_id)
    refused(db_session, "DELETE FROM knowledge_unit WHERE subject_id = :id", id=h.unit.subject_id)
    refused(db_session, "DELETE FROM question WHERE subject_id = :id", id=h.unit.subject_id)
    # The supported path, soft delete, keeps all of it.
    assert SubjectRepository(db_session, h.user.id).soft_delete(h.unit.subject_id)
    db_session.flush()
    for table in ("review_log", "grade", "attempt", "knowledge_unit", "question"):
        n = db_session.execute(
            text(f"SELECT count(*) FROM {table} WHERE user_id = :u"),
            {"u": h.user.id},
        ).scalar_one()
        assert n == 1, table


def test_tester_unit_with_cached_state_cannot_be_deleted(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # memory_state hangs on its unit with NO ACTION (D10): a unit with a cached state is retired,
    # not deleted. Red when: that FK turns CASCADE (cache and unit vanish together unnoticed).
    alice, _ = two_users
    subject, _ = SubjectRepository(db_session, alice.id).create_with_exam("Y", future_exam())
    unit = KnowledgeUnitRepository(db_session, alice.id).create(
        subject.id, title="U", summary="s", kind="concept", run_id=RUN
    )
    MemoryStateRepository(db_session, alice.id).upsert(
        unit.id, "core", FsrsScheduler().review(None, ReviewRating.GOOD, NOW)
    )
    db_session.flush()
    refused(db_session, "DELETE FROM knowledge_unit WHERE id = :id", id=unit.id)


def test_tester_session_cannot_end_in_the_past_of_its_start_boundary(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Boundary: ended_at == started_at is allowed (a session of zero seconds), one microsecond
    # before is not. Red when: CHECK `ended_at >= started_at` becomes `>` or is dropped.
    alice, _ = two_users
    sessions = ReviewSessionRepository(db_session, alice.id)
    zero = sessions.start(DAY, NOW)
    assert sessions.end(zero.id, NOW, reason="completed")
    db_session.flush()
    early = sessions.start(DAY, NOW)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        sessions.end(early.id, NOW - timedelta(microseconds=1), reason="completed")
        db_session.flush()


def test_tester_answer_length_boundary(db_session: Session, two_users: tuple[User, User]) -> None:
    # Boundary of D9: exactly 20000 characters is accepted (counted in characters, not bytes).
    # Red when: CHECK becomes `< 20000`, or `octet_length` is used for non-ASCII text.
    h = History(db_session, two_users[0])
    review = ReviewSessionRepository(db_session, h.user.id).start(DAY, NOW)
    draft = AttemptRepository(db_session, h.user.id).create_draft(review.id, h.question.id)
    db_session.flush()
    AttemptRepository(db_session, h.user.id).save_draft(
        draft.id, answer_text="ệ" * 20000, dont_remember=False
    )
    db_session.flush()


def test_tester_log_of_a_grade_cannot_use_another_users_grade_unit(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Raw SQL, Bob's log row pointing at Alice's graded unit. Red when: review_log -> grade_unit
    # FK loses user_id (the plan's P2 edge that has no raw-SQL test of its own).
    alice, bob = two_users
    ha = History(db_session, alice)
    refused(
        db_session,
        "INSERT INTO review_log (id, user_id, unit_id, facet, rating, reviewed_at, grade_id)"
        " VALUES (gen_random_uuid(), :bob, :unit, 'core', 1, now(), :grade)",
        bob=bob.id,
        unit=ha.unit.id,
        grade=ha.grade.id,
    )


def test_tester_grade_cannot_reach_a_draft_by_raw_sql_even_in_the_same_second(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # `grade_needs_submitted_attempt` must also fire for an attempt in the same transaction.
    # Red when: the trigger is dropped or its `status = 'submitted'` test is removed.
    h = History(db_session, two_users[0])
    review = ReviewSessionRepository(db_session, h.user.id).start(DAY, NOW)
    draft = AttemptRepository(db_session, h.user.id).create_draft(review.id, h.question.id)
    db_session.flush()
    refused_by_trigger(
        db_session,
        "INSERT INTO grade (id, user_id, attempt_id, source, overall)"
        " VALUES (gen_random_uuid(), :u, :a, 'system', 'forgot')",
        u=h.user.id,
        a=draft.id,
    )


# --- Gaps found by mutation: each column and each state the guards protect ---------------------


def _open_session_and_draft(session: Session, h: History) -> tuple[uuid.UUID, uuid.UUID]:
    review = ReviewSessionRepository(session, h.user.id).start(DAY, NOW)
    draft = AttemptRepository(session, h.user.id).create_draft(review.id, h.question.id)
    session.flush()
    return review.id, draft.id


def test_tester_a_draft_attempt_cannot_be_deleted(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Plan D8: every DELETE of attempt is refused, drafts too (they hold the user's text).
    # Red when: attempt_guard lets a DELETE through while OLD.status = 'draft'.
    h = History(db_session, two_users[0])
    _, draft = _open_session_and_draft(db_session, h)
    refused_by_trigger(db_session, "DELETE FROM attempt WHERE id = :id", id=draft)


def test_tester_an_open_session_cannot_be_deleted(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Plan P1: no DELETE of review_session at any time. Red when: review_session_guard refuses a
    # DELETE only after the session has ended.
    h = History(db_session, two_users[0])
    review, _ = _open_session_and_draft(db_session, h)
    refused_by_trigger(db_session, "DELETE FROM review_session WHERE id = :id", id=review)


@pytest.mark.parametrize(
    "assignment",
    [
        "stop_reason = 'user_stopped'",
        "ended_at = ended_at + interval '1 minute'",
        "ended_at = NULL, stop_reason = NULL",
    ],
)
def test_tester_an_ended_session_is_frozen_in_every_column(
    db_session: Session, two_users: tuple[User, User], assignment: str
) -> None:
    # Plan D5: a session changes only until it ends. Red when: the `OLD.ended_at IS NOT NULL`
    # test leaves review_session_guard (the other columns' tests would still pass).
    h = History(db_session, two_users[0])
    review, _ = _open_session_and_draft(db_session, h)
    assert ReviewSessionRepository(db_session, h.user.id).end(review, NOW, reason="completed")
    db_session.flush()
    refused_by_trigger(
        db_session, f"UPDATE review_session SET {assignment} WHERE id = :id", id=review
    )


@pytest.mark.parametrize(
    "assignment",
    [
        "id = gen_random_uuid()",
        "created_at = created_at - interval '1 day'",
        "learning_day = learning_day + 1",
        "started_at = started_at - interval '1 hour'",
        "user_id = :other",
    ],
)
def test_tester_an_open_session_keeps_its_keys(
    db_session: Session, two_users: tuple[User, User], assignment: str
) -> None:
    # Red when: review_session_guard stops comparing that column of NEW with OLD.
    h = History(db_session, two_users[0])
    review, _ = _open_session_and_draft(db_session, h)
    refused_by_trigger(
        db_session,
        f"UPDATE review_session SET {assignment} WHERE id = :id",
        id=review,
        other=two_users[1].id,
    )


def test_tester_a_draft_cannot_be_moved_to_another_question(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: attempt_guard drops `NEW.question_id <> OLD.question_id` (only the session id was
    # tested before).
    h = History(db_session, two_users[0])
    _, draft = _open_session_and_draft(db_session, h)
    other = QuestionRepository(db_session, h.user.id).add_idempotent(
        h.unit.subject_id, level=2, prompt="Khác?", reference_answer="a", run_id=RUN
    )
    db_session.flush()
    refused_by_trigger(
        db_session,
        "UPDATE attempt SET question_id = :q WHERE id = :id",
        q=other.id,
        id=draft,
    )


def test_tester_a_draft_cannot_change_owner(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Whatever stops it (trigger or the composite FK), a draft never changes hands. Red when:
    # both attempt_guard's owner test and the (question_id, user_id) FK are gone.
    h = History(db_session, two_users[0])
    _, draft = _open_session_and_draft(db_session, h)
    refused(
        db_session,
        "UPDATE attempt SET user_id = :other WHERE id = :id",
        id=draft,
        other=two_users[1].id,
    )


def test_tester_check_values_of_stop_reason_and_submitted_time(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: CHECK stop_reason accepts a third value; or `(status='submitted') = (submitted_at
    # IS NOT NULL)` goes (the trigger hid it for UPDATE, but INSERT has no trigger).
    h = History(db_session, two_users[0])
    review, _ = _open_session_and_draft(db_session, h)
    refused(
        db_session,
        "UPDATE review_session SET ended_at = now(), stop_reason = 'x' WHERE id = :id",
        id=review,
    )
    refused(
        db_session,
        "INSERT INTO review_session (id, user_id, learning_day, started_at, ended_at, stop_reason)"
        " VALUES (gen_random_uuid(), :u, :d, now(), now(), 'crashed')",
        u=h.user.id,
        d=DAY,
    )
    other_q = QuestionRepository(db_session, h.user.id).add_idempotent(
        h.unit.subject_id, level=3, prompt="Thêm?", reference_answer="a", run_id=RUN
    )
    db_session.flush()
    for status, at in [("submitted", "NULL"), ("draft", "now()")]:
        refused(
            db_session,
            "INSERT INTO attempt (id, user_id, review_session_id, question_id, status,"
            f" submitted_at) VALUES (gen_random_uuid(), :u, :r, :q, '{status}', {at})",
            u=h.user.id,
            r=review,
            q=other_q.id,
        )


# --- Values just outside each CHECK, on rows that would otherwise be valid ----------------------


def _fresh_graded_attempt(session: Session, h: History) -> uuid.UUID:
    """A second grade of the same attempt: no review_log yet, so a refusal below can only come
    from the CHECK under test (the first version of this test hid behind a UNIQUE violation)."""
    grade = GradeRepository(session, h.user.id).add_with_units(
        h.attempt.id,
        source="user_override",
        overall=Verdict.CORRECT,
        understanding=2,
        units={h.unit.id: Verdict.CORRECT},
        run_id=None,
    )
    session.flush()
    return grade.id


@pytest.mark.parametrize("rating", [0, 4, -1])
def test_tester_rating_outside_1_to_3_is_refused_by_its_check(
    db_session: Session, two_users: tuple[User, User], rating: int
) -> None:
    # Red when: CHECK `rating IN (1, 2, 3)` is widened (e.g. to 4 for Easy, which the product
    # does not have) or dropped.
    h = History(db_session, two_users[0])
    grade = _fresh_graded_attempt(db_session, h)
    refused(
        db_session,
        "INSERT INTO review_log (id, user_id, unit_id, facet, rating, reviewed_at, grade_id)"
        " VALUES (gen_random_uuid(), :u, :unit, 'core', :rating, now(), :grade)",
        u=h.user.id,
        unit=h.unit.id,
        rating=rating,
        grade=grade,
    )
    # And the same row with a valid rating goes in, so the refusal above was the rating.
    db_session.execute(
        text(
            "INSERT INTO review_log (id, user_id, unit_id, facet, rating, reviewed_at, grade_id)"
            " VALUES (gen_random_uuid(), :u, :unit, 'core', 3, now(), :grade)"
        ),
        {"u": h.user.id, "unit": h.unit.id, "grade": grade},
    )


@pytest.mark.parametrize("verdict", ["forgot", "excellent", ""])
def test_tester_grade_unit_verdict_outside_the_three_is_refused(
    db_session: Session, two_users: tuple[User, User], verdict: str
) -> None:
    # `forgot` is a grade-level value only (D6: the units of a forgotten answer are `incorrect`).
    # Red when: CHECK on grade_unit.verdict accepts `forgot` or anything else.
    h = History(db_session, two_users[0])
    other = KnowledgeUnitRepository(db_session, h.user.id).create(
        h.unit.subject_id, title="Khác", summary="s", kind="concept", run_id=RUN
    )
    grade = _fresh_graded_attempt(db_session, h)
    db_session.flush()
    refused(
        db_session,
        "INSERT INTO grade_unit (id, user_id, grade_id, unit_id, verdict)"
        " VALUES (gen_random_uuid(), :u, :grade, :unit, :verdict)",
        u=h.user.id,
        grade=grade,
        unit=other.id,
        verdict=verdict,
    )


@pytest.mark.parametrize("understanding", [4, 5, 100, -1])
def test_tester_understanding_has_an_upper_bound(
    db_session: Session, two_users: tuple[User, User], understanding: int
) -> None:
    # Spec us-05: three levels of understanding. Red when: CHECK `understanding BETWEEN 0 AND 3`
    # is widened or dropped. (0 is accepted by the code today; the spec names three levels, so
    # whether 0 should be allowed is left to T2.12 and not pinned here.)
    h = History(db_session, two_users[0])
    refused(
        db_session,
        "INSERT INTO grade (id, user_id, attempt_id, source, overall, understanding)"
        " VALUES (gen_random_uuid(), :u, :a, 'ai', 'correct', :n)",
        u=h.user.id,
        a=h.attempt.id,
        n=understanding,
    )


def test_tester_memory_state_phase_outside_the_enum_is_refused(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: CHECK on memory_state.phase accepts a third value (FSRS `learning`, which the
    # adapter does not produce) or is dropped.
    h = History(db_session, two_users[0])
    refused(
        db_session,
        "INSERT INTO memory_state (id, user_id, unit_id, facet, phase, stability, difficulty,"
        " due, last_review) VALUES (gen_random_uuid(), :u, :unit, 'core', 'learning', 1, 5,"
        " now(), now())",
        u=h.user.id,
        unit=h.unit.id,
    )


def test_tester_a_grade_cannot_judge_a_unit_the_question_does_not_check_even_with_all_of_its_own(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: the check in `add_with_units` becomes "every checked unit is judged" (superset),
    # which lets an extra stray unit ride along with the right ones.
    h = History(db_session, two_users[0])
    stray = KnowledgeUnitRepository(db_session, h.user.id).create(
        h.unit.subject_id, title="Lạc", summary="s", kind="concept", run_id=RUN
    )
    with pytest.raises(UnitsMismatchError):
        GradeRepository(db_session, h.user.id).add_with_units(
            h.attempt.id,
            source="ai",
            overall=Verdict.CORRECT,
            understanding=3,
            units={h.unit.id: Verdict.CORRECT, stray.id: Verdict.CORRECT},
            run_id=RUN,
        )


def test_tester_content_hash_is_pinned() -> None:
    # Stored hashes must stay stable across releases or a re-run seed duplicates every question
    # (plan D3). Red when: the "v1\n" prefix, NFC or the whitespace rule changes without a new
    # version (this value is sha256 of "v1\nTCP là gì?").

    assert content_hash("  TCP   là\tgì? ") == hashlib.sha256("v1\nTCP là gì?".encode()).hexdigest()
    assert content_hash("TCP là gì?") != hashlib.sha256("TCP là gì?".encode()).hexdigest()
