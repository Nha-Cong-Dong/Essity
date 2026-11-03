"""T5.9c: practice scheduling uses the user's ACTIVE FSRS parameters (same helper as cards,
T5.9b); a user without a fitted version gets identical results; a grade during the weekly fit
waits for the user row and then uses the new parameters (race test in test_t59c_fit_race.py)."""

from datetime import timedelta

from core_api.db.models import User
from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.fsrs_adapter import DEFAULT_PARAMETERS, FsrsScheduler
from core_api.domain.scheduling.practice import apply_rating, replay_ratings
from core_api.repositories.practice import PracticeStateRepository
from practice_rows import Practice, day

FITTED = [value * 0.4 if i < 4 else value for i, value in enumerate(DEFAULT_PARAMETERS)]
FITTED_SCHEDULER = FsrsScheduler(FITTED)


def fit(user: User) -> None:
    user.fsrs_params = {"versions": [{"version": 1, "parameters": FITTED}]}
    user.fsrs_params_version = 1


def test_domain_steps_take_the_given_scheduler() -> None:
    # Red when: apply_rating/replay_ratings ignore the scheduler and use the defaults.
    at = day(0)
    fitted = apply_rating(None, PracticeRating.GOOD, at, FITTED_SCHEDULER)
    default = apply_rating(None, PracticeRating.GOOD, at)
    assert fitted.memory.stability != default.memory.stability
    log = [(PracticeRating.GOOD, at), (PracticeRating.GOOD, at + timedelta(days=3))]
    assert replay_ratings(log, FITTED_SCHEDULER) != replay_ratings(log)


def test_record_grade_and_rebuild_use_the_fitted_parameters(practice: Practice) -> None:
    # Red when: practice grading or the rebuild schedules with default parameters.
    fit(practice.user)
    practice.session.flush()
    question = practice.question()
    done = practice.do(question, "correct", day(0))
    expected = FITTED_SCHEDULER.review(None, PracticeRating.GOOD, day(0))
    assert done.state.memory == expected
    repo = PracticeStateRepository(practice.session, practice.user.id)
    assert repo.rebuild() == 1
    state = repo.state(question.id)
    assert state is not None and state.memory == expected


def test_a_user_without_fitted_parameters_is_unchanged(practice: Practice) -> None:
    # Red when: the default path changes numbers for users with no fitted version.
    question = practice.question()
    done = practice.do(question, "correct", day(0))
    assert done.state.memory == FsrsScheduler().review(None, PracticeRating.GOOD, day(0))
