"""T5.9d: a fit (`optimize_user`) or a rollback also rebuilds the practice schedule with the
ACTIVE parameters, in the same transaction, so a question's due date does not wait for its next
grade to move onto the new curve."""

from sqlalchemy.orm import Session

from core_api.db.models import User
from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.fsrs_adapter import DEFAULT_PARAMETERS, FsrsScheduler
from core_api.domain.scheduling.params import active_parameters
from core_api.jobs.optimize_fsrs import Outcome, optimize_user, rollback_fsrs_params
from core_api.repositories.practice import PracticeStateRepository
from practice_rows import Practice, day
from scheduling.test_t59_params import NOW, forgetful_learner, seed_history

FITTED = [value * 0.4 if i < 4 else value for i, value in enumerate(DEFAULT_PARAMETERS)]


def due_of(session: Session, user: User, question_id: object) -> object:
    state = PracticeStateRepository(session, user.id).state(question_id)  # type: ignore[arg-type]
    assert state is not None
    return state.memory.due


def test_a_fit_moves_the_practice_due_date_onto_the_new_parameters(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    seed_history(db_session, alice, forgetful_learner(42))
    practice = Practice(db_session, alice)
    question = practice.question()
    practice.do(question, "correct", day(0))
    before = due_of(db_session, alice, question.id)

    assert optimize_user(db_session, alice.id, NOW) is Outcome.NEW_VERSION

    after = due_of(db_session, alice, question.id)
    assert after != before
    fitted = active_parameters(alice.fsrs_params, alice.fsrs_params_version)
    assert fitted is not None
    scheduler = FsrsScheduler(list(fitted))
    assert after == scheduler.review(None, PracticeRating.GOOD, day(0)).due
    assert bob.fsrs_params is None


def test_a_rollback_puts_the_practice_due_date_back_on_the_defaults(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    practice = Practice(db_session, alice)
    question = practice.question()
    practice.do(question, "correct", day(0))
    defaults = due_of(db_session, alice, question.id)
    alice.fsrs_params = {"versions": [{"version": 1, "parameters": FITTED}]}
    alice.fsrs_params_version = 1
    db_session.flush()
    PracticeStateRepository(db_session, alice.id).rebuild()
    assert due_of(db_session, alice, question.id) != defaults

    assert rollback_fsrs_params(db_session, alice.id) is None

    assert due_of(db_session, alice, question.id) == defaults


def test_a_user_without_practice_data_is_unaffected(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    seed_history(db_session, alice, forgetful_learner(42))
    assert optimize_user(db_session, alice.id, NOW) is Outcome.NEW_VERSION
    assert PracticeStateRepository(db_session, alice.id).list() == []
