# pyright: reportUnusedImport=false
"""T5.9b (review #163 F2): a grade during the weekly `optimize_fsrs` fit waits for the user row
the job holds, then schedules with the NEW parameters, never persisting state from the old ones."""

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session
from test_t213_grading_races import Ready, correct, ready  # noqa: F401  (fixture)

from core_api.db.models import Attempt, Grade, User
from core_api.domain.scheduling.fsrs_adapter import DEFAULT_PARAMETERS, FsrsScheduler
from core_api.domain.scheduling.rating import ReviewRating
from core_api.grading import record_grade
from core_api.repositories.review import MemoryStateRepository
from races import finished, in_thread, wait_for_lock

FITTED = [value * 0.4 if i < 4 else value for i, value in enumerate(DEFAULT_PARAMETERS)]


# Red when: record_grade does not lock the user row, so it reads the old parameters while the
# job commits new ones and the unit keeps a state computed with the old curve.
def test_a_grade_during_the_fit_uses_the_new_parameters(engine: Engine, ready: Ready) -> None:  # noqa: F811
    with Session(engine) as job, Session(engine) as grader:
        holder = job.scalars(
            select(User).where(User.id == ready.user_id).with_for_update(key_share=True)
        ).one()
        assert holder is not None
        pid = grader.execute(text("SELECT pg_backend_pid()")).scalar_one()
        user = grader.get(User, ready.user_id)  # loaded before the job commits: old parameters
        attempt = grader.get(Attempt, ready.attempts[0])
        assert user is not None and attempt is not None
        assert user.fsrs_params_version is None

        def write() -> object:
            grade = record_grade(grader, user, attempt, correct(ready.unit_id))
            grader.commit()
            return grade

        thread, outcome = in_thread(write)
        wait_for_lock(engine, pid, outcome)
        holder.fsrs_params = {"versions": [{"version": 1, "parameters": FITTED}]}
        holder.fsrs_params_version = 1
        job.commit()
        assert isinstance(finished(thread, outcome), Grade)
    with Session(engine) as check:
        state = MemoryStateRepository(check, ready.user_id).state(ready.unit_id)
        assert state is not None
        expected = FsrsScheduler(FITTED).review(None, ReviewRating.GOOD, state.last_review)
        assert state.stability == expected.stability
        assert (
            state.stability
            != FsrsScheduler().review(None, ReviewRating.GOOD, state.last_review).stability
        )
