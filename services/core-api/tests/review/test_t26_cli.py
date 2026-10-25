"""T2.6: `python -m core_api.cli rebuild-memory-state --user-email …` rebuilds one user's cache."""

import pytest
from sqlalchemy.orm import Session
from test_t26_rebuild import EXAM, Learner, reviewed_history

from core_api.cli import run
from core_api.db.models import User
from core_api.repositories.review import MemoryStateRepository


def test_t26_cli_rebuilds_the_named_users_cache(
    db_session: Session, two_users: tuple[User, User], capsys: pytest.CaptureFixture[str]
) -> None:
    learner = Learner(db_session, two_users[0])
    reviewed_history(learner, learner.subject("Mạng"), units=2, exam=EXAM)
    written = learner.states()
    MemoryStateRepository(db_session, learner.user.id).delete_all()

    assert run(db_session, ["rebuild-memory-state", "--user-email", "alice@example.com"]) == 0
    assert learner.states() == written
    assert "2" in capsys.readouterr().out


def test_t26_cli_an_unknown_email_fails_without_writing(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(db_session, ["rebuild-memory-state", "--user-email", "nobody@example.com"]) == 1
    assert "no user" in capsys.readouterr().err
