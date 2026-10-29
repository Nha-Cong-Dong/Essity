"""T5.3 tester: edges the coder's tests leave open. Live grading and override must rate units
under the *current* rule, not a pinned one, and every live path must agree with a full replay
(plan-review R1: one source of truth)."""

import uuid
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
    version="tester-harsher",
    rating_by_verdict={**Q20_TAM.rating_by_verdict, Verdict.PARTIAL: ReviewRating.AGAIN},
)
STRICT = replace(
    Q20_TAM,
    version="tester-strict",
    rating_by_verdict={**Q20_TAM.rating_by_verdict, Verdict.CORRECT: ReviewRating.HARD},
)


@pytest.fixture
def desk(db_session: Session, two_users: tuple[User, User]) -> Desk:
    return Desk(db_session, two_users[0], units=3)


def states(desk: Desk) -> dict[uuid.UUID, MemoryState | None]:
    repo = MemoryStateRepository(desk.session, desk.user.id)
    return {unit: repo.state(unit) for unit in desk.units}


def ratings_of(desk: Desk, grade_id: uuid.UUID) -> dict[uuid.UUID, int]:
    query = select(ReviewLog.unit_id, ReviewLog.rating).where(ReviewLog.grade_id == grade_id)
    return dict(desk.session.execute(query).tuples().all())


# US-05 AC9 with three different verdicts. Red when: partial shares a rating or a state with
# correct or incorrect, or the ratings land on the wrong unit.
def test_ac9_correct_partial_incorrect_give_three_ratings_and_ordered_due_dates(
    desk: Desk,
) -> None:
    a, b, c = desk.units
    outcome = desk.grade(desk.submitted(), Stub(verdicts={b: "partial", c: "incorrect"}))
    assert outcome.grade is not None
    assert ratings_of(desk, outcome.grade.id) == {
        a: ReviewRating.GOOD,
        b: ReviewRating.HARD,
        c: ReviewRating.AGAIN,
    }
    now = states(desk)
    sa, sb, sc = now[a], now[b], now[c]
    assert sa is not None and sb is not None and sc is not None
    assert sc.due <= sb.due <= sa.due
    assert len({sa, sb, sc}) == 3


# R1: live grading follows current_rule(). Red when: record_grade pins Q20_TAM (or any rule
# other than the current one), so after a rule change the live log and state disagree with what
# rebuild() makes of the same history.
def test_live_grading_after_a_rule_change_rates_and_schedules_under_the_new_rule(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(multi_unit, "CURRENT_RULE", HARSHER)
    outcome = desk.grade(desk.submitted(), Stub(verdicts={desk.units[1]: "partial"}))
    assert outcome.grade is not None
    assert ratings_of(desk, outcome.grade.id)[desk.units[1]] == ReviewRating.AGAIN
    live = states(desk)
    MemoryStateRepository(desk.session, desk.user.id).rebuild()
    assert states(desk) == live


# R1: override follows current_rule(). Red when: override_grade rates its units under a pinned
# rule instead of the current one.
def test_override_after_a_rule_change_logs_ratings_under_the_new_rule(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = desk.submitted()
    desk.grade(attempt, Stub(verdicts={desk.units[0]: "partial"}))
    grade = GradeRepository(desk.session, desk.user.id).latest_for_attempt(attempt)
    assert grade is not None
    monkeypatch.setattr(multi_unit, "CURRENT_RULE", STRICT)
    new = override_grade(desk.session, desk.user, grade.id, "correct")
    desk.session.flush()
    assert set(ratings_of(desk, new.id).values()) == {ReviewRating.HARD}


# R1 over a mixed history. Red when: any live path (in-time grade, forgot, late answer,
# override) writes a state that a full replay of review_log does not reproduce, e.g. a stale
# grade's grade_unit rows join into the replay, or the forgot path rates differently from its
# stored unit verdicts.
def test_mixed_history_live_states_equal_a_full_replay(desk: Desk) -> None:
    a, b, c = desk.units
    desk.grade(desk.submitted(days_ago=6), Stub(verdicts={b: "partial"}))
    desk.grade(desk.submitted(days_ago=4, forgot=True), Stub())
    overridden = desk.submitted(days_ago=2)
    desk.grade(overridden, Stub(verdicts={a: "incorrect", c: "partial"}))
    desk.grade(desk.submitted(), Stub(verdicts={c: "incorrect"}))
    desk.grade(desk.submitted(days_ago=3), Stub(verdicts={a: "partial"}))  # late
    grade = GradeRepository(desk.session, desk.user.id).latest_for_attempt(overridden)
    assert grade is not None
    override_grade(desk.session, desk.user, grade.id, "correct")
    desk.session.flush()
    live = states(desk)
    assert all(state is not None for state in live.values())
    MemoryStateRepository(desk.session, desk.user.id).rebuild()
    assert states(desk) == live


# Determinism across rules over the same mixed history. Red when: a rule replay is not undone by
# replaying under the current rule again (some state leaks between replays).
def test_rule_round_trip_over_a_mixed_history_restores_every_state(desk: Desk) -> None:
    a, b, _ = desk.units
    desk.grade(desk.submitted(days_ago=5), Stub(verdicts={a: "partial"}))
    desk.grade(desk.submitted(days_ago=1), Stub(verdicts={b: "partial"}))
    repo = MemoryStateRepository(desk.session, desk.user.id)
    original = states(desk)
    repo.rebuild(rule=HARSHER)
    assert states(desk) != original
    repo.rebuild(rule=STRICT)
    repo.rebuild()
    assert states(desk) == original
