"""T2.13 edges of `grade_attempt` found by mutating the code (tester, 26/10)."""

import pytest
from sqlalchemy.orm import Session
from test_t213_grade_attempt import Desk, Stub

from core_api.db.models import Grade, GradeUnit, ReviewLog, User
from core_api.repositories.review import (
    GradeRepository,
    MemoryStateRepository,
    UnitsMismatchError,
)
from core_api.repositories.subject import SubjectNotFoundError


@pytest.fixture
def desk(db_session: Session, two_users: tuple[User, User]) -> Desk:
    return Desk(db_session, two_users[0], units=2)


# Plan 🟡12. Red when: a unit set changed under the grading (UnitsMismatchError) or a subject
# gone meanwhile is reported "unavailable" (a retry would clear it) instead of "invalid", or
# leaves part of the grade behind.
@pytest.mark.parametrize("error", [UnitsMismatchError("units"), SubjectNotFoundError("subject")])
def test_t213_units_changed_under_the_grading_is_invalid_and_writes_nothing(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    attempt = desk.submitted()

    def changed(*_: object, **__: object) -> None:
        raise error

    monkeypatch.setattr(GradeRepository, "add_with_units", changed)
    outcome = desk.grade(attempt, Stub())
    assert (outcome.grading, outcome.failure) == ("failed", "invalid")
    assert (desk.count(Grade), desk.count(GradeUnit), desk.count(ReviewLog)) == (0, 0, 0)


# Plan D-11 (rebuild by unit). Red when: `rebuild(unit_ids=...)` drops the cache of every unit of
# the subject but replays only the units asked for: a late "Chấm lại" on one unit would wipe the
# schedule of the others.
def test_t213_rebuilding_some_units_keeps_the_others_schedule(desk: Desk) -> None:
    desk.grade(desk.submitted(days_ago=1), Stub())
    states = MemoryStateRepository(desk.session, desk.user.id)
    kept, replayed = desk.units[1], desk.units[0]
    before = states.state(kept)
    assert before is not None
    states.rebuild(subject_id=desk.subject.id, unit_ids=[replayed])
    assert states.state(kept) == before
    assert states.state(replayed) is not None
