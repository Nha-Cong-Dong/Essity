"""T5.R tester edges: a level-2/3 answer leaves an existing schedule exactly as it was, including
the "Không nhớ" path that never calls the AI, and an answer graded late."""

import uuid

import pytest
from sqlalchemy.orm import Session
from test_t213_grade_attempt import RUN, Desk, Stub

from core_api.db.models import Grade, ReviewLog, User
from core_api.domain.scheduling.fsrs_adapter import MemoryState
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import MemoryStateRepository


@pytest.fixture
def desk(db_session: Session, two_users: tuple[User, User]) -> Desk:
    return Desk(db_session, two_users[0], units=2)


def states(desk: Desk) -> dict[uuid.UUID, MemoryState | None]:
    repo = MemoryStateRepository(desk.session, desk.user.id)
    return {unit: repo.state(unit) for unit in desk.units}


def to_level(desk: Desk, level: int) -> None:
    """Point the desk at a new question of `level` on the same units."""
    desk.question = QuestionRepository(desk.session, desk.user.id).add_idempotent(
        desk.subject.id, level=level, prompt=f"Mức {level}?", reference_answer="a", run_id=RUN
    )
    for unit in desk.units:
        QuestionUnitRepository(desk.session, desk.user.id).link(desk.question.id, unit)
    desk.session.flush()


@pytest.mark.parametrize("forgot", [False, True])
@pytest.mark.parametrize("level", [2, 3])
# Red when: a level-2/3 answer (graded wrong, or "Không nhớ") after a level-1 one adds a review_log
# row or moves the existing memory_state (due, stability, last_review...).
def test_t5r_higher_answer_leaves_an_existing_schedule_untouched(
    desk: Desk, level: int, forgot: bool
) -> None:
    desk.grade(desk.submitted(days_ago=2), Stub())
    before, logs_before = states(desk), desk.count(ReviewLog)
    assert all(state is not None for state in before.values())
    to_level(desk, level)

    attempt = desk.submitted("sai", forgot=forgot)
    desk.grade(attempt, Stub(verdicts={unit: "incorrect" for unit in desk.units}))

    assert desk.count(Grade) == 2  # the practice grade is kept
    assert desk.count(ReviewLog) == logs_before
    assert states(desk) == before


# Red when: a level-2 answer submitted before the unit's last review (the late path, which
# replays the unit) moves the schedule or logs a review.
def test_t5r_a_late_higher_answer_does_not_replay_the_unit(desk: Desk) -> None:
    level_one = desk.question
    to_level(desk, 2)
    late = desk.submitted("sai", days_ago=3)  # answered before the level-1 review below
    desk.question = level_one
    desk.grade(desk.submitted(days_ago=1), Stub())
    before, logs_before = states(desk), desk.count(ReviewLog)

    desk.grade(late, Stub(verdicts={unit: "incorrect" for unit in desk.units}))

    assert desk.count(ReviewLog) == logs_before
    assert states(desk) == before
