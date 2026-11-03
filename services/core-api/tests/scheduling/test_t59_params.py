"""T5.9: per-user FSRS parameters. Pure part: versions and rollback, and a fit that must beat the
defaults on a learner whose memory the defaults mispredict."""

import random
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core_api.domain.scheduling.fsrs_adapter import DEFAULT_PARAMETERS, FsrsScheduler
from core_api.domain.scheduling.params import (
    MIN_SCORED_REVIEWS,
    NothingToRollBackError,
    Reviews,
    active_parameters,
    add_version,
    fit_parameters,
    previous_version,
)
from core_api.domain.scheduling.rating import ReviewRating

START = datetime(2026, 9, 1, 13, 0, tzinfo=UTC)
GAPS = (0, 1, 3, 7, 14, 30)  # days between reviews of one unit


def forgetful_learner(units: int, seed: int = 7) -> list[Reviews]:
    """Reviews of a learner whose true stability is 40% of the defaults': a recall that the
    default scheduler overrates."""
    rng = random.Random(seed)
    truth = FsrsScheduler(
        [*(value * 0.4 for value in DEFAULT_PARAMETERS[:4]), *DEFAULT_PARAMETERS[4:]]
    )
    result: list[Reviews] = []
    for _ in range(units):
        state = None
        at = START
        reviews: list[tuple[ReviewRating, datetime]] = []
        for gap in GAPS:
            at += timedelta(days=gap)
            recalled = state is None or rng.random() < truth.retrievability(state, at)
            rating = ReviewRating.GOOD if recalled else ReviewRating.AGAIN
            reviews.append((rating, at))
            state = truth.review(state, rating, at)
        result.append(reviews)
    return result


def test_too_little_history_keeps_the_defaults() -> None:
    units = forgetful_learner(3)
    assert sum(len(unit) - 1 for unit in units) < MIN_SCORED_REVIEWS
    assert fit_parameters(units) is None


def test_fit_beats_the_defaults_on_the_users_own_history() -> None:
    units = forgetful_learner(60)
    fit = fit_parameters(units)
    assert fit is not None
    assert fit.loss < fit.baseline_loss
    assert fit.scored_reviews == 60 * (len(GAPS) - 1)
    assert fit.parameters != tuple(DEFAULT_PARAMETERS)
    # Only the three groups move; the rest stay on the defaults.
    unchanged = [4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    assert all(fit.parameters[i] == DEFAULT_PARAMETERS[i] for i in unchanged)


def test_a_fit_starting_from_the_best_known_parameters_finds_nothing_more() -> None:
    units = forgetful_learner(60)
    first = fit_parameters(units)
    assert first is not None
    again = fit_parameters(units, first.parameters)
    assert again is None or again.loss < first.loss


def test_versions_are_numbered_kept_and_rolled_back() -> None:
    at = START
    history, first = add_version(None, [1.0] * 21, scored_reviews=300, loss=0.5, at=at)
    history, second = add_version(history, [2.0] * 21, scored_reviews=400, loss=0.4, at=at)
    assert (first, second) == (1, 2)
    assert active_parameters(history, 2) == (2.0,) * 21
    assert active_parameters(history, 1) == (1.0,) * 21
    assert active_parameters(history, None) is None
    assert previous_version(history, 2) == 1
    assert previous_version(history, 1) is None  # back to the defaults
    with pytest.raises(NothingToRollBackError):
        previous_version(history, None)
    # A fit after a rollback never reuses a number.
    history, third = add_version(history, [3.0] * 21, scored_reviews=500, loss=0.3, at=at)
    assert third == 3


def test_only_the_last_five_versions_are_kept() -> None:
    history: dict[str, Any] | None = None
    number = 0
    for _ in range(7):
        history, number = add_version(history, [1.0] * 21, scored_reviews=1, loss=0.1, at=START)
    assert history is not None
    assert number == 7
    assert [entry["version"] for entry in history["versions"]] == [3, 4, 5, 6, 7]


# --- the job, on real tables -------------------------------------------------------------------

import uuid  # noqa: E402
from datetime import date  # noqa: E402

from sqlalchemy.orm import Session  # noqa: E402

from core_api.db.models import User  # noqa: E402
from core_api.domain.scheduling.rating import Verdict  # noqa: E402
from core_api.jobs.optimize_fsrs import Outcome, optimize_user, rollback_fsrs_params  # noqa: E402
from core_api.repositories.question import (  # noqa: E402
    QuestionRepository,
    QuestionUnitRepository,
)
from core_api.repositories.review import (  # noqa: E402
    AttemptRepository,
    GradeRepository,
    MemoryStateRepository,
    ReviewLogRepository,
    ReviewSessionRepository,
)
from core_api.repositories.subject import SubjectRepository  # noqa: E402
from core_api.repositories.unit import KnowledgeUnitRepository  # noqa: E402

RUN = uuid.uuid4()
EXAM = date(2027, 3, 1)
VERDICT = {
    ReviewRating.GOOD: Verdict.CORRECT,
    ReviewRating.HARD: Verdict.PARTIAL,
    ReviewRating.AGAIN: Verdict.INCORRECT,
}
NOW = datetime(2026, 12, 1, tzinfo=UTC)


def seed_history(session: Session, user: User, histories: list[Reviews]) -> None:
    """Write each unit's reviews through the real tables (review_log only; the schedule is built
    by the job's rebuild, as after a regrade)."""
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Subject", EXAM)
    sessions = ReviewSessionRepository(session, user.id)
    attempts = AttemptRepository(session, user.id)
    grades = GradeRepository(session, user.id)
    logs = ReviewLogRepository(session, user.id)
    for number, reviews in enumerate(histories):
        unit = KnowledgeUnitRepository(session, user.id).create(
            subject.id, title=f"u{number}", summary="s", kind="concept", run_id=RUN
        )
        question = QuestionRepository(session, user.id).add_idempotent(
            subject.id, level=1, prompt=f"q{number}?", reference_answer="a", run_id=RUN
        )
        QuestionUnitRepository(session, user.id).link(question.id, unit.id)
        for rating, at in reviews:
            sitting = sessions.start(at.date(), at)
            attempt = attempts.create_draft(sitting.id, question.id)
            attempts.submit(attempt.id, at)
            grade = grades.add_with_units(
                attempt.id,
                source="ai",
                overall=VERDICT[rating],
                understanding=None,
                units={unit.id: VERDICT[rating]},
                run_id=RUN,
            )
            logs.append(unit.id, rating=rating, reviewed_at=at, grade_id=grade.id)
            sessions.end(sitting.id, at, reason="completed")
    session.flush()


def schedule(session: Session, user: User) -> list[tuple[float, datetime]]:
    repo = MemoryStateRepository(session, user.id)
    rows = [repo.state(row.unit_id) for row in repo.list()]
    return sorted((row.stability, row.due) for row in rows if row is not None)


def test_a_user_without_enough_history_keeps_the_defaults(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    seed_history(db_session, alice, forgetful_learner(3))
    assert optimize_user(db_session, alice.id, NOW) is Outcome.NOT_ENOUGH_HISTORY
    assert alice.fsrs_params is None and alice.fsrs_params_version is None


def test_new_parameters_are_versioned_rebuild_the_schedule_and_roll_back(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    seed_history(db_session, alice, forgetful_learner(42))
    seed_history(db_session, bob, forgetful_learner(3))
    MemoryStateRepository(db_session, alice.id).rebuild()
    defaults = schedule(db_session, alice)

    assert optimize_user(db_session, alice.id, NOW) is Outcome.NEW_VERSION
    assert alice.fsrs_params_version == 1
    fitted = active_parameters(alice.fsrs_params, 1)
    assert fitted is not None and fitted != tuple(DEFAULT_PARAMETERS)
    assert schedule(db_session, alice) != defaults  # replayed with the fitted parameters

    # Running again finds nothing new to store (same history, starting from version 1).
    assert optimize_user(db_session, alice.id, NOW) is Outcome.NO_IMPROVEMENT
    assert alice.fsrs_params_version == 1

    assert rollback_fsrs_params(db_session, alice.id) is None  # version 1 -> the defaults
    assert alice.fsrs_params_version is None
    assert schedule(db_session, alice) == defaults  # the schedule is back as it was
    with pytest.raises(NothingToRollBackError):
        rollback_fsrs_params(db_session, alice.id)

    # Another user is untouched.
    assert bob.fsrs_params is None and bob.fsrs_params_version is None
