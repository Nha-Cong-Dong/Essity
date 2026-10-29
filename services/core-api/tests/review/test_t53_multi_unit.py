"""T5.3: a three-unit question schedules each unit by its own verdict, and every rebuild path
follows the current rule (Q20 tạm), so changing the rule replays review_log to the new states."""

import uuid
from collections.abc import Iterator
from dataclasses import replace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t213_grade_attempt import Desk, Stub

from core_api.db.models import ReviewLog, User
from core_api.domain.scheduling import multi_unit
from core_api.domain.scheduling.fsrs_adapter import MemoryState
from core_api.domain.scheduling.multi_unit import Q20_TAM
from core_api.domain.scheduling.rating import ReviewRating, Verdict
from core_api.overriding import override_grade
from core_api.repositories.review import GradeRepository, MemoryStateRepository

HARSHER = replace(
    Q20_TAM,
    version="test-harsher",
    rating_by_verdict={**Q20_TAM.rating_by_verdict, Verdict.PARTIAL: ReviewRating.AGAIN},
)


@pytest.fixture
def desk(db_session: Session, two_users: tuple[User, User]) -> Desk:
    return Desk(db_session, two_users[0], units=3)


@pytest.fixture
def harsher_current(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(multi_unit, "CURRENT_RULE", HARSHER)
    yield


def states(desk: Desk) -> dict[uuid.UUID, MemoryState | None]:
    repo = MemoryStateRepository(desk.session, desk.user.id)
    return {unit: repo.state(unit) for unit in desk.units}


def logged(desk: Desk) -> dict[uuid.UUID, int]:
    return dict(desk.session.execute(select(ReviewLog.unit_id, ReviewLog.rating)).tuples().all())


# US-05 AC9, PRD AC5. Red when: the three units share one rating or one state.
def test_ac9_three_unit_question_two_right_one_wrong_each_unit_gets_own_schedule(
    desk: Desk,
) -> None:
    desk.grade(desk.submitted(), Stub(verdicts={desk.units[2]: "incorrect"}))
    assert logged(desk) == {
        desk.units[0]: ReviewRating.GOOD,
        desk.units[1]: ReviewRating.GOOD,
        desk.units[2]: ReviewRating.AGAIN,
    }
    now = states(desk)
    assert now[desk.units[0]] == now[desk.units[1]]
    wrong, right = now[desk.units[2]], now[desk.units[0]]
    assert wrong is not None and right is not None
    assert wrong.due < right.due


# Red when: the override path rates units by anything but the rule, or leaves the wrong state.
def test_ac9_override_of_a_three_unit_question_rates_every_unit_under_the_rule(
    desk: Desk,
) -> None:
    attempt = desk.submitted()
    desk.grade(attempt, Stub(verdicts={desk.units[2]: "incorrect"}))
    grade = GradeRepository(desk.session, desk.user.id).latest_for_attempt(attempt)
    assert grade is not None
    override_grade(desk.session, desk.user, grade.id, "correct")
    desk.session.flush()
    rows = desk.session.execute(select(ReviewLog.rating)).scalars().all()
    assert sorted(rows) == [ReviewRating.AGAIN] + [ReviewRating.GOOD] * 5
    now = states(desk)
    assert len({now[u] for u in desk.units}) == 1  # the override made all three Good


# Red when: replay is not repeatable.
def test_rebuild_twice_under_the_same_rule_gives_identical_states(desk: Desk) -> None:
    desk.grade(desk.submitted(days_ago=3), Stub(verdicts={desk.units[1]: "partial"}))
    desk.grade(desk.submitted(), Stub(verdicts={desk.units[2]: "incorrect"}))
    repo = MemoryStateRepository(desk.session, desk.user.id)
    repo.rebuild()
    first = states(desk)
    repo.rebuild()
    assert states(desk) == first


# Red when: rebuild keeps using the stored rating, so a rule change changes nothing.
def test_changing_rule_replays_review_log_to_new_states_and_back(desk: Desk) -> None:
    desk.grade(desk.submitted(), Stub(verdicts={desk.units[1]: "partial"}))
    repo = MemoryStateRepository(desk.session, desk.user.id)
    original = states(desk)
    rows_before = logged(desk)
    repo.rebuild(rule=HARSHER)
    harsher = states(desk)
    assert harsher[desk.units[1]] != original[desk.units[1]]  # partial now counts as Again
    assert harsher[desk.units[0]] == original[desk.units[0]]
    assert logged(desk) == rows_before  # review_log is append-only: replay never writes it
    repo.rebuild()
    assert states(desk) == original


# Red when: only rebuild(rule=) knows the new rule and the default paths (moved exam, override,
# late grade, CLI) mix old stored ratings back in (plan-review R1).
def test_default_rebuild_after_a_rule_change_follows_the_current_rule(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk.grade(desk.submitted(), Stub(verdicts={desk.units[1]: "partial"}))
    repo = MemoryStateRepository(desk.session, desk.user.id)
    repo.rebuild(rule=HARSHER)
    expected = states(desk)
    monkeypatch.setattr(multi_unit, "CURRENT_RULE", HARSHER)
    repo.rebuild()
    assert states(desk) == expected


# ADR-0001. Red when: one user's replay touches another's schedule.
def test_rebuild_under_rule_leaves_the_other_user_alone(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    mine, other = Desk(db_session, two_users[0], units=3), Desk(db_session, two_users[1], units=3)
    other.grade(other.submitted(), Stub(verdicts={other.units[1]: "partial"}))
    before = states(other)
    mine.grade(mine.submitted(), Stub())
    MemoryStateRepository(db_session, mine.user.id).rebuild(rule=HARSHER)
    assert states(other) == before
