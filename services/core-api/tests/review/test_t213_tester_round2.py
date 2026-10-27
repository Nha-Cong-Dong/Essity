"""T2.13 edges of `grade_attempt` found by mutating the code (tester round 2, 28/10)."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t213_grade_attempt import Desk, Stub

from core_api.db.models import Grade, GradeUnit, ReviewLog, User
from core_api.repositories.review import GradeRepository, MemoryStateRepository


@pytest.fixture
def desk(db_session: Session, two_users: tuple[User, User]) -> Desk:
    return Desk(db_session, two_users[0], units=2)


# US-05 AC2 ("1–3 ý thiếu hoặc sai"). Red when: `record_grade` drops the AI's `missing` points,
# so the result screen shows a partial answer with nothing to work on.
def test_us05_ac2_what_was_missing_is_stored_with_the_grade(desk: Desk) -> None:
    attempt = desk.submitted()
    outcome = desk.grade(attempt, Stub(verdicts={desk.units[1]: "incorrect"}))
    assert outcome.grade is not None
    stored = GradeRepository(desk.session, desk.user.id).latest_for_attempt(attempt)
    assert stored is not None and stored.missing == ["ý thiếu"]


# Plan "Giao dịch và khóa" 2.8 (rollback, answer kept, "Chấm lại" offered). Red when: a write
# failing half-way is reported "invalid" (no "Chấm lại") instead of "unavailable".
def test_t213_a_write_failing_half_way_is_unavailable_not_invalid(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = desk.submitted()

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(MemoryStateRepository, "upsert", broken)
    outcome = desk.grade(attempt, Stub())
    assert (outcome.grading, outcome.failure) == ("failed", "unavailable")


# US-04 AC2, plan 2.1 ("đã có grade hợp lệ → trả luôn"). Red when: "Chấm lại" on a "Không nhớ"
# that is already graded writes a second system grade and a second Again in review_log: the
# unit's schedule would be pushed back once per click.
def test_us04_ac2_regrading_dont_remember_twice_writes_one_grade(desk: Desk) -> None:
    attempt = desk.submitted(forgot=True)
    first = desk.grade(attempt, Stub())
    second = desk.grade(attempt, Stub())
    assert first.grade is not None and second.grade is not None
    assert second.grade.id == first.grade.id
    assert (desk.count(Grade), desk.count(GradeUnit), desk.count(ReviewLog)) == (1, 2, 2)
    logged = desk.session.scalars(select(ReviewLog.grade_id)).all()
    assert set(logged) == {first.grade.id}
