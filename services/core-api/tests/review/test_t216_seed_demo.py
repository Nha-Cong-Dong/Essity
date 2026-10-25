"""T2.16 (plan D-10): `python -m core_api.cli seed-demo --user-email …` gives one user a subject to
review by hand, with the fake grader. Local and test only: it writes made-up study material."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from core_api.cli import run
from core_api.db.models import Anchor, KnowledgeUnit, Question, QuestionUnit, Subject, User
from core_api.demo import DEMO_SUBJECT


def counts(session: Session, user: User) -> tuple[int, int, int]:
    """(subjects, questions, units) of the user."""

    def count(owner: InstrumentedAttribute[uuid.UUID]) -> int:
        return session.scalar(select(func.count()).where(owner == user.id)) or 0

    return count(Subject.user_id), count(Question.user_id), count(KnowledgeUnit.user_id)


# Red when: the seeded questions cannot be graded (a unit without a source, US-05 AC8) or no
# question spans two units (US-05 AC9 by hand).
def test_t216_seed_demo_gives_the_user_questions_that_can_be_graded(
    db_session: Session, two_users: tuple[User, User], capsys: pytest.CaptureFixture[str]
) -> None:
    alice, bob = two_users
    assert run(db_session, ["seed-demo", "--user-email", alice.email], environment="local") == 0
    subjects, questions, units = counts(db_session, alice)
    assert (subjects, questions) == (1, 3) and units >= 3
    assert (
        db_session.scalar(select(Subject.name).where(Subject.user_id == alice.id)) == DEMO_SUBJECT
    )
    unit_ids = db_session.scalars(
        select(KnowledgeUnit.id).where(KnowledgeUnit.user_id == alice.id)
    ).all()
    for unit_id in unit_ids:
        assert db_session.scalar(select(func.count()).where(Anchor.unit_id == unit_id)), unit_id
    per_question = db_session.execute(
        select(QuestionUnit.question_id, func.count())
        .where(QuestionUnit.user_id == alice.id)
        .group_by(QuestionUnit.question_id)
    ).all()
    assert len(per_question) == 3 and max(n for _, n in per_question) >= 2
    assert counts(db_session, bob) == (0, 0, 0)
    assert "3" in capsys.readouterr().out


def test_t216_seed_demo_twice_adds_nothing(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    assert run(db_session, ["seed-demo", "--user-email", alice.email], environment="test") == 0
    assert run(db_session, ["seed-demo", "--user-email", alice.email], environment="test") == 0
    assert counts(db_session, alice)[:2] == (1, 3)


# Plan D-10. Red when: made-up material can be written into a real user's account.
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_t216_seed_demo_refuses_outside_local_and_test(
    db_session: Session,
    two_users: tuple[User, User],
    environment: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alice = two_users[0]
    assert run(db_session, ["seed-demo", "--user-email", alice.email], environment=environment) == 1
    assert counts(db_session, alice) == (0, 0, 0)
    assert "local" in capsys.readouterr().err


def test_t216_seed_demo_unknown_email_fails(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        run(db_session, ["seed-demo", "--user-email", "nobody@example.com"], environment="local")
        == 1
    )
    assert "no user" in capsys.readouterr().err
