"""T5.R: only level-1 answers move FSRS. A grade of a level-2 or level-3 question is stored but
writes no review_log row and no memory_state; an override of it and a rebuild leave memory alone;
a review_log row left from before (logged by an earlier version) is not replayed."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session
from test_t213_grade_attempt import RUN, Desk, Stub

from clock import FROZEN_NOW
from core_api.db.models import Grade, ReviewLog, User
from core_api.domain.scheduling.fsrs_adapter import MemoryState
from core_api.domain.scheduling.rating import ReviewRating
from core_api.overriding import override_grade
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    GradeRepository,
    MemoryStateRepository,
    ReviewLogRepository,
)


@pytest.fixture
def desk(db_session: Session, two_users: tuple[User, User]) -> Desk:
    return Desk(db_session, two_users[0], units=2)


def states(desk: Desk) -> dict[uuid.UUID, MemoryState | None]:
    repo = MemoryStateRepository(desk.session, desk.user.id)
    return {unit: repo.state(unit) for unit in desk.units}


def logs(desk: Desk) -> int:
    return desk.count(ReviewLog)


@pytest.mark.parametrize("level", [2, 3])
# Red when: a level-2/3 grade creates review_log rows or a memory_state.
def test_grade_of_a_higher_question_is_stored_but_does_not_move_fsrs(
    desk: Desk, level: int
) -> None:
    desk.question.level = level
    desk.session.flush()
    outcome = desk.grade(desk.submitted(), Stub())
    assert outcome.grading == "graded"
    assert desk.count(Grade) == 1
    assert logs(desk) == 0
    assert states(desk) == {unit: None for unit in desk.units}


# Red when: a level-1 grade stops scheduling (the guard is too wide).
def test_grade_of_a_level_1_question_still_moves_fsrs(desk: Desk) -> None:
    desk.grade(desk.submitted(), Stub())
    assert logs(desk) == 2
    assert all(state is not None for state in states(desk).values())


# Red when: an override of a level-2 or level-3 grade writes review_log or memory_state.
@pytest.mark.parametrize("level", [2, 3])
def test_override_of_a_higher_grade_does_not_move_fsrs(desk: Desk, level: int) -> None:
    desk.question.level = level
    desk.session.flush()
    attempt = desk.submitted()
    desk.grade(attempt, Stub(verdicts={desk.units[1]: "incorrect"}))
    grade = GradeRepository(desk.session, desk.user.id).latest_for_attempt(attempt)
    assert grade is not None
    override_grade(desk.session, desk.user, grade.id, "correct")
    desk.session.flush()
    assert desk.count(Grade) == 2  # the override is stored
    assert logs(desk) == 0
    assert states(desk) == {unit: None for unit in desk.units}


# Red when: rebuild replays a review_log row whose question is level 2 or 3 (data written by
# an earlier version): the unit's state must come from level-1 answers only.
def test_rebuild_ignores_logs_of_higher_questions_already_in_the_database(desk: Desk) -> None:
    desk.grade(desk.submitted(days_ago=3), Stub())
    desk.question.level = 2  # the same rows, as an older version left them
    desk.session.flush()
    repo = MemoryStateRepository(desk.session, desk.user.id)
    assert repo.rebuild() == 0
    assert states(desk) == {unit: None for unit in desk.units}


# Red when: a unit with a level-1 answer and a legacy level-2 log is replayed with both.
def test_rebuild_keeps_the_level_1_history_beside_a_legacy_level_2_log(desk: Desk) -> None:
    desk.grade(desk.submitted(days_ago=3), Stub())
    level_one_only = states(desk)
    first = desk.question
    desk.question = QuestionRepository(desk.session, desk.user.id).add_idempotent(
        desk.subject.id, level=2, prompt="Áp dụng TCP?", reference_answer="a", run_id=RUN
    )
    for unit in desk.units:
        QuestionUnitRepository(desk.session, desk.user.id).link(desk.question.id, unit)
    attempt = desk.submitted(days_ago=1)
    desk.grade(attempt, Stub(verdicts={desk.units[0]: "incorrect"}))
    assert desk.question is not first and logs(desk) == 2  # the level-2 grade logged nothing
    grade = GradeRepository(desk.session, desk.user.id).latest_for_attempt(attempt)
    assert grade is not None
    for unit in desk.units:  # what an earlier version wrote
        ReviewLogRepository(desk.session, desk.user.id).append(
            unit,
            rating=ReviewRating.AGAIN,
            reviewed_at=FROZEN_NOW - timedelta(days=1),
            grade_id=grade.id,
        )
    desk.session.flush()
    MemoryStateRepository(desk.session, desk.user.id).rebuild()
    assert states(desk) == level_one_only
