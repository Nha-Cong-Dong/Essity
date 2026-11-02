"""T2.2, changing what is already seeded (decision with flow-expert, 26/10): never in place.
Without the flag a changed question refuses the file and names the line; with `--replace-changed`
the old question is retired (its history stays) and a new one takes over."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models import Question, QuestionUnit, User
from core_api.domain.question_hash import content_hash
from core_api.domain.scheduling.rating import Verdict
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import (
    AttemptRepository,
    GradeRepository,
    ReviewSessionRepository,
)
from test_seed import VALID, counts, seed, subject_of, write

CHANGED = VALID.replace("Bắt tay ba bước.", "Bắt tay ba bước, SYN rồi SYN-ACK rồi ACK.")


def questions_of(session: Session, user: User) -> list[Question]:
    # created_at is now() = the test transaction's start, so every row ties on it; without the
    # level tiebreak the order (and `[0]` below) follows heap order and flakes.
    return list(
        session.scalars(
            select(Question)
            .where(Question.user_id == user.id)
            .order_by(Question.created_at, Question.level)
        )
    )


# Red when: a changed answer is applied without being asked, or the refusal hides the line.
def test_t22_a_changed_answer_is_refused_with_its_line_and_the_flag(
    db_session: Session,
    two_users: tuple[User, User],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    seed(db_session, alice, subject_id, write(tmp_path, VALID))
    capsys.readouterr()
    assert seed(db_session, alice, subject_id, write(tmp_path, CHANGED)) == 1
    err = capsys.readouterr().err
    assert "line 18" in err and "--replace-changed" in err
    assert {q.reference_answer for q in questions_of(db_session, alice)} == {
        "Bắt tay ba bước.",
        "TCP bắt tay, UDP không.",
    }


# Red when: replacing loses the history of the old question, leaves two active questions with
# one hash, links the new one to other units, or a second run adds more.
def test_t22_replace_changed_retires_the_old_question_and_keeps_its_history(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    seed(db_session, alice, subject_id, write(tmp_path, VALID))
    old = questions_of(db_session, alice)[0]
    unit_id = db_session.scalars(
        select(QuestionUnit.unit_id).where(QuestionUnit.question_id == old.id)
    ).one()
    at = datetime(2026, 10, 1, 13, 0, tzinfo=UTC)
    sitting = ReviewSessionRepository(db_session, alice.id).start(at.date(), at)
    attempts = AttemptRepository(db_session, alice.id)
    attempt = attempts.create_draft(sitting.id, old.id)
    attempts.submit(attempt.id, at)
    GradeRepository(db_session, alice.id).add_with_units(
        attempt.id,
        source="ai",
        overall=Verdict.CORRECT,
        understanding=None,
        units={unit_id: Verdict.CORRECT},
        run_id=None,
    )
    db_session.flush()
    path = write(tmp_path, CHANGED)
    assert seed(db_session, alice, subject_id, path, "--replace-changed") == 0
    rows = questions_of(db_session, alice)
    assert len(rows) == 3
    assert db_session.get(Question, old.id).status == "retired"  # type: ignore[union-attr]
    new = next(q for q in rows if q.status == "active" and q.prompt == old.prompt)
    assert new.reference_answer.startswith("Bắt tay ba bước,")
    linked = db_session.scalars(
        select(QuestionUnit.unit_id).where(QuestionUnit.question_id == new.id)
    ).all()
    assert list(linked) == [unit_id]
    assert attempts.get(attempt.id) is not None  # the old answer and its grade stay
    assert seed(db_session, alice, subject_id, path, "--replace-changed") == 0
    assert len(questions_of(db_session, alice)) == 3


# Red when: a level change is not seen as a change like an answer change.
def test_t22_a_changed_level_counts_as_a_change(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    seed(db_session, alice, subject_id, write(tmp_path, VALID))
    relevelled = write(tmp_path, VALID.replace("level: 2", "level: 3"))
    assert seed(db_session, alice, subject_id, relevelled) == 1
    assert seed(db_session, alice, subject_id, relevelled, "--replace-changed") == 0
    active = [q.level for q in questions_of(db_session, alice) if q.status == "active"]
    assert sorted(active) == [1, 3]


# Red when: a question the user dropped ("Bỏ câu này", T2.18) is brought back, or the whole file
# fails because of it (running the whole file again is routine).
def test_t22_a_retired_question_is_skipped_not_revived_and_not_an_error(
    db_session: Session,
    two_users: tuple[User, User],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    path = write(tmp_path, VALID)
    seed(db_session, alice, subject_id, path)
    dropped = questions_of(db_session, alice)[0]
    QuestionRepository(db_session, alice.id).retire(dropped.id)
    capsys.readouterr()
    assert seed(db_session, alice, subject_id, path) == 0
    assert "retired" in capsys.readouterr().out
    assert len(questions_of(db_session, alice)) == 2
    assert [q.status for q in questions_of(db_session, alice)].count("active") == 1
    assert seed(db_session, alice, subject_id, write(tmp_path, CHANGED), "--replace-changed") == 0
    assert db_session.get(Question, dropped.id).status == "retired"  # type: ignore[union-attr]
    assert len(questions_of(db_session, alice)) == 2


# Red when: a refused file writes anything, or two changed questions are reported one at a time.
def test_t22_a_refused_file_writes_nothing_and_reports_every_changed_question(
    db_session: Session,
    two_users: tuple[User, User],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    seed(db_session, alice, subject_id, write(tmp_path, VALID))
    both = CHANGED.replace("TCP bắt tay, UDP không.", "Khác.")
    capsys.readouterr()
    assert seed(db_session, alice, subject_id, write(tmp_path, both)) == 1
    err = capsys.readouterr().err
    assert "line 18" in err and "line 22" in err
    assert counts(db_session, alice)[2] == 2


# Red when: two active questions of one subject can share a content hash, or a retired one blocks
# the new one in the database itself.
def test_t22_the_database_allows_one_active_question_per_hash(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    raw = {"user": alice.id, "subject": subject_id, "hash": content_hash("Q?"), "run": uuid.uuid4()}
    insert = text(
        "INSERT INTO question (id, user_id, subject_id, level, prompt, reference_answer, status,"
        " content_hash, run_id) VALUES (gen_random_uuid(), :user, :subject, 1, 'Q?', 'a',"
        " :status, :hash, :run)"
    )
    db_session.execute(insert, {**raw, "status": "retired"})
    db_session.execute(insert, {**raw, "status": "retired"})
    db_session.execute(insert, {**raw, "status": "active"})
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(insert, {**raw, "status": "active"})
