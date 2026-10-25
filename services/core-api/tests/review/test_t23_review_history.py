"""T2.3: review history (layer 3, append-only) and memory_state (layer 4), plan
`docs/plans/t2.1-t2.3-units-review-history.md` (D1, D2, D5–D10; review plan P1–P4).

The data side of us-04 AC2, us-05 AC9 and us-08; their behaviour comes with T2.9, T2.12, T2.13.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from types import FunctionType
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clock import future_exam, spare_day
from core_api.db.models import Grade, User
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, Phase
from core_api.domain.scheduling.rating import ReviewRating, Verdict
from core_api.jobs.purge_unverified import UNVERIFIED_LIFETIME, purge_unverified
from core_api.repositories.base import AppendOnlyError, UserScopedRepository
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    AttemptNotDraftError,
    AttemptNotSubmittedError,
    AttemptRepository,
    GradeRepository,
    MemoryStateRepository,
    ReviewLogRepository,
    ReviewSessionEndedError,
    ReviewSessionItemRepository,
    ReviewSessionRepository,
    UnitsMismatchError,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository, UnitNotFoundError
from core_api.repositories.user import UserRepository
from isolation import assert_isolated

RUN = uuid.uuid4()
NOW = datetime(2026, 10, 23, 1, 0, tzinfo=UTC)
DAY = date(2026, 10, 23)


# --- A small history to work on -----------------------------------------------------------------


class History:
    """One user's subject, unit, question, session, submitted attempt, grade and review_log."""

    def __init__(self, session: Session, user: User) -> None:
        self.session, self.user = session, user
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam())
        self.unit = KnowledgeUnitRepository(session, user.id).create(
            subject.id, title="TCP", summary="s", kind="concept", run_id=RUN
        )
        self.question = QuestionRepository(session, user.id).add_idempotent(
            subject.id, level=1, prompt="TCP là gì?", reference_answer="a", run_id=RUN
        )
        QuestionUnitRepository(session, user.id).link(self.question.id, self.unit.id)
        self.review = ReviewSessionRepository(session, user.id).start(DAY, NOW)
        attempts = AttemptRepository(session, user.id)
        self.attempt = attempts.create_draft(self.review.id, self.question.id)
        attempts.save_draft(self.attempt.id, answer_text="Tin cậy", dont_remember=False)
        attempts.submit(self.attempt.id, NOW)
        self.grade = GradeRepository(session, user.id).add_with_units(
            self.attempt.id,
            source="ai",
            overall=Verdict.CORRECT,
            understanding=3,
            units={self.unit.id: Verdict.CORRECT},
            run_id=RUN,
        )
        self.log = ReviewLogRepository(session, user.id).append(
            self.unit.id, rating=ReviewRating.GOOD, reviewed_at=NOW, grade_id=self.grade.id
        )
        session.flush()


@pytest.fixture
def history(db_session: Session, two_users: tuple[User, User]) -> History:
    return History(db_session, two_users[0])


def refused(session: Session, sql: str, /, **params: Any) -> None:
    """The statement is refused by the database (a trigger or a constraint)."""
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(text(sql), params)


def refused_by_trigger(session: Session, sql: str, /, **params: Any) -> None:
    """Refused by an append-only trigger itself, not by a key or a CHECK that happens to fire."""
    with pytest.raises(IntegrityError, match="is refused"), session.begin_nested():
        session.execute(text(sql), params)


# --- attempt (T2.3 "Xong khi", us-04) ----------------------------------------------------------


def test_t23_attempt_unique_per_session_question(db_session: Session, history: History) -> None:
    # One attempt per (session, question): opening it again returns that attempt (T2.15 (c)), and
    # the database still refuses a second row inserted around the repository.
    again, made = AttemptRepository(db_session, history.user.id).open_draft(
        history.review.id, history.question.id
    )
    assert (again.id, made) == (history.attempt.id, False)
    refused(
        db_session,
        "INSERT INTO attempt (id, user_id, review_session_id, question_id, status)"
        " VALUES (gen_random_uuid(), :u, :s, :q, 'draft')",
        u=history.user.id,
        s=history.review.id,
        q=history.question.id,
    )


def test_us04_attempt_submitted_requires_timestamp(db_session: Session, history: History) -> None:
    refused(
        db_session, "UPDATE attempt SET submitted_at = NULL WHERE id = :id", id=history.attempt.id
    )


def test_t23_attempt_updatable_only_while_draft(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    h = History(db_session, alice)
    attempts = AttemptRepository(db_session, alice.id)
    # Submitted: no more edits through the repository, nor in SQL.
    with pytest.raises(AttemptNotDraftError):
        attempts.save_draft(h.attempt.id, answer_text="sửa sau khi nộp", dont_remember=False)
    refused_by_trigger(
        db_session, "UPDATE attempt SET answer_text = 'x' WHERE id = :id", id=h.attempt.id
    )


def test_t23_a_draft_cannot_change_its_keys(db_session: Session, history: History) -> None:
    draft = AttemptRepository(db_session, history.user.id).create_draft(
        ReviewSessionRepository(db_session, history.user.id).start(spare_day(), NOW).id,
        history.question.id,
    )
    db_session.flush()
    other = ReviewSessionRepository(db_session, history.user.id).start(spare_day(), NOW)
    db_session.flush()
    refused_by_trigger(
        db_session,
        "UPDATE attempt SET review_session_id = :other WHERE id = :id",
        other=other.id,
        id=draft.id,
    )


def test_t23_text_of_an_answer_is_capped(db_session: Session, history: History) -> None:
    draft = AttemptRepository(db_session, history.user.id).create_draft(
        ReviewSessionRepository(db_session, history.user.id).start(spare_day(), NOW).id,
        history.question.id,
    )
    db_session.flush()
    refused(
        db_session,
        "UPDATE attempt SET answer_text = repeat('a', 20001) WHERE id = :id",
        id=draft.id,
    )


# --- The append-only triggers (T2.3 "Xong khi", review plan P1) ---------------------------------

ROW_STATEMENTS = {
    "grade update": "UPDATE grade SET overall = 'partial' WHERE id = :grade",
    "grade delete": "DELETE FROM grade WHERE id = :grade",
    "grade_unit update": "UPDATE grade_unit SET verdict = 'partial' WHERE grade_id = :grade",
    "grade_unit delete": "DELETE FROM grade_unit WHERE grade_id = :grade",
    "review_log update": "UPDATE review_log SET rating = 1 WHERE id = :log",
    "review_log delete": "DELETE FROM review_log WHERE id = :log",
    "attempt delete": "DELETE FROM attempt WHERE id = :attempt",
    "session delete": "DELETE FROM review_session WHERE id = :session",
    "session update after end": "UPDATE review_session SET learning_day = :day WHERE id = :session",
}


@pytest.mark.parametrize("statement", sorted(ROW_STATEMENTS))
def test_t23_history_rows_cannot_be_changed_or_deleted(
    db_session: Session, history: History, statement: str
) -> None:
    # Red when: a trigger is missing, or lets this statement through.
    ReviewSessionRepository(db_session, history.user.id).end(
        history.review.id, NOW, reason="completed"
    )
    db_session.flush()
    refused_by_trigger(
        db_session,
        ROW_STATEMENTS[statement],
        grade=history.grade.id,
        log=history.log.id,
        attempt=history.attempt.id,
        session=history.review.id,
        day=DAY + timedelta(days=1),
    )


@pytest.mark.parametrize(
    "table", ["grade", "grade_unit", "review_log", "attempt", "review_session"]
)
def test_t23_truncate_rejected(db_session: Session, history: History, table: str) -> None:
    refused_by_trigger(db_session, f"TRUNCATE {table} CASCADE")


def test_t23_on_conflict_do_update_rejected_on_review_log(
    db_session: Session, history: History
) -> None:
    # An upsert is an UPDATE in disguise: the row trigger catches it all the same.
    refused_by_trigger(
        db_session,
        "INSERT INTO review_log (id, user_id, unit_id, facet, rating, reviewed_at, grade_id)"
        " VALUES (gen_random_uuid(), :user, :unit, 'core', 1, now(), :grade)"
        " ON CONFLICT (grade_id, unit_id, facet) DO UPDATE SET rating = 1",
        user=history.user.id,
        unit=history.unit.id,
        grade=history.grade.id,
    )


def test_t23_owner_cannot_delete_history_rows_directly(
    db_session: Session, history: History
) -> None:
    refused_by_trigger(
        db_session, "DELETE FROM review_log WHERE user_id = :user", user=history.user.id
    )


def test_t23_user_with_history_cannot_be_deleted_until_t222(
    db_session: Session, history: History
) -> None:
    # Plan D1: no way around the triggers yet, not even deleting the account; T2.22 opens one
    # for a database role of its own, core_eraser. Red when: a delete path slips through first.
    refused_by_trigger(db_session, 'DELETE FROM "user" WHERE id = :user', user=history.user.id)
    refused_by_trigger(db_session, 'TRUNCATE "user" CASCADE')


def test_t23_unit_with_history_cannot_be_deleted(db_session: Session, history: History) -> None:
    # Plan D10: NO ACTION from layer 3 to layer 2. A unit that was reviewed is retired, never
    # deleted, or its history would go with it.
    refused(db_session, "DELETE FROM knowledge_unit WHERE id = :unit", unit=history.unit.id)


def test_t23_purge_still_runs_when_other_users_have_history(
    db_session: Session, history: History
) -> None:
    # Review plan P4: purge deletes unverified accounts in one statement; a verified user's
    # history elsewhere must not make it fail.
    stale = UserRepository(db_session).create(f"purge-{uuid.uuid4().hex[:12]}@example.com")
    stale.created_at = NOW - UNVERIFIED_LIFETIME - timedelta(days=1)
    db_session.flush()
    assert purge_unverified(db_session, NOW) >= 1


# --- Repositories of layer 3 change nothing (T2.3 "Xong khi") ------------------------------------

APPEND_ONLY = [
    ReviewSessionRepository,
    ReviewSessionItemRepository,
    AttemptRepository,
    GradeRepository,
    ReviewLogRepository,
]
# Every public method each adds to the base repository: closing a session, editing a draft, and
# otherwise only adding and reading. A new name here is a change to the append-only rule.
OWN_METHODS = {
    # T2.9: one open session per learning day (plan C4) is made or found, never changed.
    ReviewSessionRepository: {"start", "end", "open_for_day", "open_on", "hold_for_update"},
    ReviewSessionItemRepository: {"add_all", "of_session", "progress"},
    AttemptRepository: {"create_draft", "open_draft", "save_draft", "submit"},
    GradeRepository: {
        "add_with_units",
        "latest_for_attempt",
        "try_lock_attempt",
        "is_being_graded",
        "unit_verdicts",
        "graded",
    },
    ReviewLogRepository: {"append"},
}


@pytest.mark.parametrize("repository", APPEND_ONLY, ids=lambda cls: cls.__name__)
def test_t23_append_only_repositories_have_no_mutators(repository: type) -> None:
    # Red when: a method such as GradeRepository.amend() or ReviewLogRepository.correct() is
    # added, whatever its name (final ce93f48 #4).
    base = {name for name in dir(UserScopedRepository) if not name.startswith("_")}
    names = {
        name
        for name in dir(repository)
        if not name.startswith("_") and isinstance(getattr(repository, name), FunctionType)
    }
    assert names - base == OWN_METHODS[repository]


@pytest.mark.parametrize("repository", APPEND_ONLY, ids=lambda cls: cls.__name__)
def test_t23_delete_raises(db_session: Session, history: History, repository: type) -> None:
    with pytest.raises(AppendOnlyError):
        repository(db_session, history.user.id).delete(uuid.uuid4())


def test_t23_latest_grade_is_newest_seq(db_session: Session, history: History) -> None:
    # Plan D2: two grades in one transaction share created_at; seq still orders them.
    grades = GradeRepository(db_session, history.user.id)
    override = grades.add_with_units(
        history.attempt.id,
        source="user_override",
        overall=Verdict.PARTIAL,
        understanding=2,
        units={history.unit.id: Verdict.PARTIAL},
        run_id=None,
    )
    db_session.flush()
    latest = grades.latest_for_attempt(history.attempt.id)
    assert latest is not None and latest.id == override.id
    assert not hasattr(Grade, "is_current")


# --- grade (us-04 AC2, us-05 AC9; D6) ----------------------------------------------------------


def test_us04_ac2_dont_remember_grade_is_system_forgot(
    db_session: Session, history: History
) -> None:
    # "Không nhớ" writes a grade of its own, so review_log always has one (D6).
    grades = GradeRepository(db_session, history.user.id)
    forgot = grades.add_with_units(
        history.attempt.id,
        source="system",
        overall=Verdict.FORGOT,
        understanding=None,
        units={history.unit.id: Verdict.INCORRECT},
        run_id=None,
    )
    db_session.flush()
    assert (forgot.source, forgot.overall) == ("system", "forgot")
    for source, overall in [("ai", "forgot"), ("system", "correct")]:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            grades.add_with_units(
                history.attempt.id,
                source=source,
                overall=Verdict(overall),
                understanding=None,
                units={history.unit.id: Verdict.INCORRECT},
                run_id=None,
            )
            db_session.flush()


def test_t23_understanding_hidden_when_wrong_or_forgot(
    db_session: Session, history: History
) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        GradeRepository(db_session, history.user.id).add_with_units(
            history.attempt.id,
            source="ai",
            overall=Verdict.INCORRECT,
            understanding=2,
            units={history.unit.id: Verdict.INCORRECT},
            run_id=RUN,
        )
        db_session.flush()


def test_us05_ac9_one_grade_unit_per_unit(db_session: Session, history: History) -> None:
    refused(
        db_session,
        "INSERT INTO grade_unit (id, user_id, grade_id, unit_id, verdict)"
        " VALUES (gen_random_uuid(), :user, :grade, :unit, 'correct')",
        user=history.user.id,
        grade=history.grade.id,
        unit=history.unit.id,
    )


def test_t23_review_log_needs_a_graded_unit(db_session: Session, history: History) -> None:
    # Review plan P2: a log row points at a unit this grade judged, so replay (T2.6) finds it.
    other = KnowledgeUnitRepository(db_session, history.user.id).create(
        history.unit.subject_id, title="UDP", summary="s", kind="concept", run_id=RUN
    )
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        ReviewLogRepository(db_session, history.user.id).append(
            other.id, rating=ReviewRating.AGAIN, reviewed_at=NOW, grade_id=history.grade.id
        )
        db_session.flush()


# --- review_session (us-08; D5) ----------------------------------------------------------------


def test_us08_stop_reason_set_iff_ended(db_session: Session, history: History) -> None:
    refused(
        db_session,
        "UPDATE review_session SET stop_reason = 'completed' WHERE id = :id",
        id=history.review.id,
    )
    ended = ReviewSessionRepository(db_session, history.user.id).end(
        history.review.id, NOW, reason="user_stopped"
    )
    assert ended
    db_session.flush()


def test_us08_a_session_ends_once(db_session: Session, history: History) -> None:
    sessions = ReviewSessionRepository(db_session, history.user.id)
    assert sessions.end(history.review.id, NOW, reason="completed")
    db_session.flush()
    assert not sessions.end(history.review.id, NOW, reason="user_stopped")


@pytest.mark.parametrize("reason", ["completed", "user_stopped"])
@pytest.mark.parametrize("write", ["create_draft", "save_draft", "submit"])
def test_us08_an_ended_session_takes_no_more_answers(
    db_session: Session, history: History, reason: str, write: str
) -> None:
    # Its summary and study time were already shown; a second tab writing late would change them
    # (final ce93f48 #5, plan D14). The draft left open stays as it was. Red when: the repository
    # writes an attempt without checking that its session is still open.
    sessions = ReviewSessionRepository(db_session, history.user.id)
    attempts = AttemptRepository(db_session, history.user.id)
    review = sessions.start(spare_day(), NOW)
    draft = attempts.create_draft(review.id, history.question.id)
    attempts.save_draft(draft.id, answer_text="dở", dont_remember=False)
    other = QuestionRepository(db_session, history.user.id).add_idempotent(
        history.question.subject_id, level=1, prompt="UDP là gì?", reference_answer="a", run_id=RUN
    )
    assert sessions.end(review.id, NOW + timedelta(minutes=5), reason=reason)
    with pytest.raises(ReviewSessionEndedError):
        if write == "create_draft":
            attempts.create_draft(review.id, other.id)
        elif write == "save_draft":
            attempts.save_draft(draft.id, answer_text="muộn", dont_remember=False)
        else:
            attempts.submit(draft.id, NOW + timedelta(minutes=10))
    kept = db_session.execute(
        text("SELECT answer_text, status FROM attempt WHERE review_session_id = :s"),
        {"s": review.id},
    ).all()
    assert [tuple(row) for row in kept] == [("dở", "draft")]


def test_us08_a_submitted_answer_in_an_ended_session_reports_the_session(
    db_session: Session, history: History
) -> None:
    # The order of the errors is fixed: not found, then session ended, then not a draft.
    assert ReviewSessionRepository(db_session, history.user.id).end(
        history.review.id, NOW, reason="completed"
    )
    with pytest.raises(ReviewSessionEndedError):
        AttemptRepository(db_session, history.user.id).submit(history.attempt.id, NOW)


# --- The CHECKs follow the domain enums (review plan P3) ----------------------------------------


@pytest.mark.parametrize("verdict", [v for v in Verdict if v is not Verdict.FORGOT])
def test_checks_accept_every_unit_verdict(
    db_session: Session, history: History, verdict: Verdict
) -> None:
    # Red when: Verdict gains a value the grade_unit CHECK does not know.
    GradeRepository(db_session, history.user.id).add_with_units(
        history.attempt.id,
        source="ai",
        overall=Verdict.PARTIAL,
        understanding=1,
        units={history.unit.id: verdict},
        run_id=RUN,
    )
    db_session.flush()


@pytest.mark.parametrize("rating", list(ReviewRating))
def test_checks_accept_every_rating(
    db_session: Session, history: History, rating: ReviewRating
) -> None:
    grade = GradeRepository(db_session, history.user.id).add_with_units(
        history.attempt.id,
        source="user_override",
        overall=Verdict.CORRECT,
        understanding=3,
        units={history.unit.id: Verdict.CORRECT},
        run_id=None,
    )
    ReviewLogRepository(db_session, history.user.id).append(
        history.unit.id, rating=rating, reviewed_at=NOW, grade_id=grade.id
    )
    db_session.flush()


def test_checks_refuse_values_outside_the_enums(db_session: Session, history: History) -> None:
    params = {"user": history.user.id, "attempt": history.attempt.id, "unit": history.unit.id}
    refused(
        db_session,
        "INSERT INTO grade (id, user_id, attempt_id, source, overall) VALUES"
        " (gen_random_uuid(), :user, :attempt, 'ai', 'excellent')",
        **params,
    )
    refused(
        db_session,
        "INSERT INTO review_log (id, user_id, unit_id, facet, rating, reviewed_at, grade_id)"
        " SELECT gen_random_uuid(), :user, :unit, 'core', 4, now(), id FROM grade"
        " WHERE attempt_id = :attempt",
        **params,
    )


# --- memory_state (layer 4) --------------------------------------------------------------------


def test_t23_memory_state_phase_step_roundtrip(db_session: Session, history: History) -> None:
    scheduler = FsrsScheduler()
    first = scheduler.review(None, ReviewRating.GOOD, NOW)
    lapsed = scheduler.review(first, ReviewRating.AGAIN, NOW + timedelta(days=3))
    assert (first.phase, lapsed.phase) == (Phase.REVIEW, Phase.RELEARNING)
    states = MemoryStateRepository(db_session, history.user.id)
    for state in (first, lapsed):
        states.upsert(history.unit.id, "core", state)
        db_session.flush()
        db_session.expire_all()
        assert states.state(history.unit.id, "core") == state


def test_t23_memory_state_unique_unit_facet(db_session: Session, history: History) -> None:
    states = MemoryStateRepository(db_session, history.user.id)
    states.upsert(history.unit.id, "core", FsrsScheduler().review(None, ReviewRating.GOOD, NOW))
    db_session.flush()
    refused(
        db_session,
        "INSERT INTO memory_state (id, user_id, unit_id, facet, phase, stability, difficulty,"
        " due, last_review) VALUES (gen_random_uuid(), :user, :unit, 'core', 'review', 1, 5,"
        " now(), now())",
        user=history.user.id,
        unit=history.unit.id,
    )


def test_t23_step_iff_relearning(db_session: Session, history: History) -> None:
    for phase, step in [("relearning", None), ("review", 0)]:
        refused(
            db_session,
            "INSERT INTO memory_state (id, user_id, unit_id, facet, phase, step, stability,"
            " difficulty, due, last_review) VALUES (gen_random_uuid(), :user, :unit, 'core',"
            " :phase, :step, 1, 5, now(), now())",
            user=history.user.id,
            unit=history.unit.id,
            phase=phase,
            step=step,
        )


def test_t23_memory_state_facet_is_core_only(db_session: Session, history: History) -> None:
    refused(
        db_session,
        "INSERT INTO memory_state (id, user_id, unit_id, facet, phase, stability, difficulty,"
        " due, last_review) VALUES (gen_random_uuid(), :user, :unit, 'level-2', 'review', 1, 5,"
        " now(), now())",
        user=history.user.id,
        unit=history.unit.id,
    )


def test_us02b_ac4_review_log_survives_adding_anchor(db_session: Session, history: History) -> None:
    from core_api.repositories.unit import AnchorRepository

    AnchorRepository(db_session, history.user.id).create(
        history.unit.id, source="notes", quote_text="Ghi chú mới", run_id=RUN
    )
    db_session.flush()
    assert ReviewLogRepository(db_session, history.user.id).get(history.log.id) is not None


# --- Isolation (ADR-0001) ----------------------------------------------------------------------


def _assert_append_only_isolated(
    session: Session, repository: type, owner: User, other: User, made: Any
) -> None:
    theirs = repository(session, other.id)
    assert theirs.get(made.id) is None, "B read A's row"
    assert made.id not in {row.id for row in theirs.list()}, "B listed A's row"
    with pytest.raises(AppendOnlyError):
        theirs.delete(made.id)
    assert repository(session, owner.id).get(made.id) is not None


def test_t23_isolation_layer_3(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    h = History(db_session, alice)
    for repository, made in [
        (ReviewSessionRepository, h.review),
        (AttemptRepository, h.attempt),
        (GradeRepository, h.grade),
        (ReviewLogRepository, h.log),
    ]:
        _assert_append_only_isolated(db_session, repository, alice, bob, made)


def test_t23_isolation_memory_state(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    h = History(db_session, alice)
    state = FsrsScheduler().review(None, ReviewRating.GOOD, NOW)
    assert_isolated(
        db_session,
        MemoryStateRepository,
        alice,
        bob,
        lambda states: states.upsert(h.unit.id, "core", state),
    )


def test_t23_bob_cannot_attach_to_alices_session_or_question(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    h = History(db_session, alice)
    refused(
        db_session,
        "INSERT INTO attempt (id, user_id, review_session_id, question_id, status)"
        " VALUES (gen_random_uuid(), :bob, :session, :question, 'draft')",
        bob=bob.id,
        session=h.review.id,
        question=h.question.id,
    )


# --- Every link between two users' tables carries user_id (review plan P2) ----------------------


def test_every_fk_between_user_owned_tables_includes_user_id(db_session: Session) -> None:
    # Red when: a foreign key between two tables of user data is on the id alone, so a row of one
    # user can point at another user's.
    inspector = inspect(db_session.connection())
    owned = {
        t
        for t in inspector.get_table_names()
        if "user_id" in {c["name"] for c in inspector.get_columns(t)}
    }
    single = [
        (table, fk["referred_table"], fk["constrained_columns"])
        for table in owned
        for fk in inspector.get_foreign_keys(table)
        if fk["referred_table"] in owned
        and fk["referred_table"] != "user"
        and "user_id" not in fk["constrained_columns"]
    ]
    assert single == []


# --- Review 31074ea ------------------------------------------------------------------------------


def test_t23_bob_cannot_overwrite_alices_memory_state(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: the upsert conflicts on (unit_id, facet) alone and updates Alice's row in place,
    # never checking the composite key of the row it would have inserted (review 🔴).
    alice, bob = two_users
    h = History(db_session, alice)
    hers = FsrsScheduler().review(None, ReviewRating.GOOD, NOW)
    MemoryStateRepository(db_session, alice.id).upsert(h.unit.id, "core", hers)
    db_session.flush()
    with pytest.raises((UnitNotFoundError, IntegrityError)), db_session.begin_nested():
        MemoryStateRepository(db_session, bob.id).upsert(
            h.unit.id, "core", FsrsScheduler().review(None, ReviewRating.AGAIN, NOW)
        )
    db_session.expire_all()
    assert MemoryStateRepository(db_session, alice.id).state(h.unit.id) == hers


def test_t23_a_draft_cannot_be_graded(db_session: Session, history: History) -> None:
    # Red when: a draft gets a grade, then its text still changes under it (review 🟠).
    draft = AttemptRepository(db_session, history.user.id).create_draft(
        ReviewSessionRepository(db_session, history.user.id).start(spare_day(), NOW).id,
        history.question.id,
    )
    with pytest.raises(AttemptNotSubmittedError):
        GradeRepository(db_session, history.user.id).add_with_units(
            draft.id,
            source="ai",
            overall=Verdict.CORRECT,
            understanding=3,
            units={history.unit.id: Verdict.CORRECT},
            run_id=RUN,
        )
    refused_by_trigger(
        db_session,
        "INSERT INTO grade (id, user_id, attempt_id, source, overall) VALUES"
        " (gen_random_uuid(), :user, :attempt, 'ai', 'correct')",
        user=history.user.id,
        attempt=draft.id,
    )


def test_t23_grade_units_are_exactly_the_questions_units(
    db_session: Session, history: History
) -> None:
    # Red when: a grade judges a unit the question does not check, so replay (T2.6) schedules an
    # unrelated unit (review 🟡).
    stray = KnowledgeUnitRepository(db_session, history.user.id).create(
        history.unit.subject_id, title="UDP", summary="s", kind="concept", run_id=RUN
    )
    grades = GradeRepository(db_session, history.user.id)
    for units in ({stray.id: Verdict.CORRECT}, {}):
        with pytest.raises(UnitsMismatchError):
            grades.add_with_units(
                history.attempt.id,
                source="ai",
                overall=Verdict.CORRECT,
                understanding=3,
                units=units,
                run_id=RUN,
            )


def test_t23_units_cannot_be_added_to_an_old_grade(db_session: Session, history: History) -> None:
    # A grade's verdicts are written with it, in one transaction; a later one is a new grade.
    old = db_session.execute(
        text(
            "INSERT INTO grade (id, user_id, attempt_id, source, overall, created_at) VALUES"
            " (gen_random_uuid(), :user, :attempt, 'user_override', 'partial',"
            " now() - interval '1 day') RETURNING id"
        ),
        {"user": history.user.id, "attempt": history.attempt.id},
    ).scalar_one()
    refused_by_trigger(
        db_session,
        "INSERT INTO grade_unit (id, user_id, grade_id, unit_id, verdict)"
        " VALUES (gen_random_uuid(), :user, :grade, :unit, 'partial')",
        user=history.user.id,
        grade=old,
        unit=history.unit.id,
    )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE attempt SET id = gen_random_uuid() WHERE id = :attempt",
        "UPDATE attempt SET created_at = now() - interval '1 day' WHERE id = :attempt",
        "UPDATE review_session SET created_at = now() - interval '1 day' WHERE id = :session",
    ],
)
def test_t23_ids_and_creation_times_never_change(
    db_session: Session, two_users: tuple[User, User], statement: str
) -> None:
    alice, _ = two_users
    sessions = ReviewSessionRepository(db_session, alice.id)
    review = sessions.start(spare_day(), NOW)
    h = History(db_session, alice)
    draft = AttemptRepository(db_session, alice.id).create_draft(review.id, h.question.id)
    db_session.flush()
    refused_by_trigger(db_session, statement, attempt=draft.id, session=review.id)


def test_us08_a_session_cannot_end_before_it_started(db_session: Session, history: History) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        ReviewSessionRepository(db_session, history.user.id).end(
            history.review.id, NOW - timedelta(hours=1), reason="completed"
        )


# --- Trigger functions resolve the real tables (review final fed95f2) ----------------------------


def test_t23_a_temporary_table_cannot_stand_in_for_attempt(
    db_session: Session, history: History
) -> None:
    # Red when: the trigger functions look tables up on the caller's search_path, where pg_temp
    # comes first, so a temporary "attempt" saying "submitted" lets a draft be graded.
    draft = AttemptRepository(db_session, history.user.id).create_draft(
        ReviewSessionRepository(db_session, history.user.id).start(spare_day(), NOW).id,
        history.question.id,
    )
    with pytest.raises(IntegrityError, match="is refused"), db_session.begin_nested():
        db_session.execute(text("CREATE TEMP TABLE attempt (id uuid, status text)"))
        db_session.execute(
            text("INSERT INTO attempt (id, status) VALUES (:id, 'submitted')"), {"id": draft.id}
        )
        db_session.execute(
            text(
                "INSERT INTO public.grade (id, user_id, attempt_id, source, overall) VALUES"
                " (gen_random_uuid(), :user, :attempt, 'ai', 'correct')"
            ),
            {"user": history.user.id, "attempt": draft.id},
        )


def test_t23_a_temporary_table_cannot_stand_in_for_grade(
    db_session: Session, history: History
) -> None:
    # Red when: a temporary "grade" dated now() lets verdicts join an old grade.
    old = db_session.execute(
        text(
            "INSERT INTO grade (id, user_id, attempt_id, source, overall, created_at) VALUES"
            " (gen_random_uuid(), :user, :attempt, 'user_override', 'partial',"
            " now() - interval '1 day') RETURNING id"
        ),
        {"user": history.user.id, "attempt": history.attempt.id},
    ).scalar_one()
    with pytest.raises(IntegrityError, match="is refused"), db_session.begin_nested():
        db_session.execute(text("CREATE TEMP TABLE grade (id uuid, created_at timestamptz)"))
        db_session.execute(
            text("INSERT INTO grade (id, created_at) VALUES (:id, now())"), {"id": old}
        )
        db_session.execute(
            text(
                "INSERT INTO public.grade_unit (id, user_id, grade_id, unit_id, verdict)"
                " VALUES (gen_random_uuid(), :user, :grade, :unit, 'partial')"
            ),
            {"user": history.user.id, "grade": old, "unit": history.unit.id},
        )


# T2.13 (migration 0011, PLAN T2.13 23/10b, PR B B1): the fake grader's grades are stored as
# source 'fake'; understanding is 1..3, never 0. Red when: the CHECKs are not changed.
def test_t213_fake_grades_are_stored_as_fake(db_session: Session, history: History) -> None:
    made = GradeRepository(db_session, history.user.id).add_with_units(
        history.attempt.id,
        source="fake",
        overall=Verdict.CORRECT,
        understanding=3,
        units={history.unit.id: Verdict.CORRECT},
        run_id=RUN,
    )
    db_session.flush()
    assert made.source == "fake"


@pytest.mark.parametrize(
    ("understanding", "stored"), [(0, False), (1, True), (3, True), (4, False)]
)
def test_t213_understanding_is_one_to_three(
    db_session: Session, history: History, understanding: int, stored: bool
) -> None:
    def add() -> None:
        GradeRepository(db_session, history.user.id).add_with_units(
            history.attempt.id,
            source="ai",
            overall=Verdict.CORRECT,
            understanding=understanding,
            units={history.unit.id: Verdict.CORRECT},
            run_id=RUN,
        )
        db_session.flush()

    if stored:
        with db_session.begin_nested():
            add()
    else:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            add()
