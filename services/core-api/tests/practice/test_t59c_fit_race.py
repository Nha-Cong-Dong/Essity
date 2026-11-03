# pyright: reportUnusedImport=false
"""T5.9c: a practice grade during the weekly `optimize_fsrs` fit waits for the user row the job
holds, then schedules with the NEW parameters (same lock order as `grading.record_grade`)."""

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_practice_races import Ready, pid_of, ready, record, stored  # noqa: F401  (fixture)

from core_api.db.models import User
from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.fsrs_adapter import DEFAULT_PARAMETERS, FsrsScheduler
from practice_rows import day
from races import finished, in_thread, wait_for_lock

FITTED = [value * 0.4 if i < 4 else value for i, value in enumerate(DEFAULT_PARAMETERS)]


# Red when: practice record_grade does not lock the user row first, so it schedules with the old
# parameters while the job commits new ones.
def test_a_practice_grade_during_the_fit_uses_the_new_parameters(
    engine: Engine,
    ready: Ready,  # noqa: F811
) -> None:
    with Session(engine) as job, Session(engine) as grader:
        holder = job.scalars(
            select(User).where(User.id == ready.user_id).with_for_update(key_share=True)
        ).one()
        pid = pid_of(grader)
        stale = grader.get(User, ready.user_id)  # loaded before the job commits: old parameters
        assert stale is not None and stale.fsrs_params_version is None

        def write() -> object:
            state = record(grader, ready, 0)
            grader.commit()
            return state

        thread, outcome = in_thread(write)
        wait_for_lock(engine, pid, outcome)
        holder.fsrs_params = {"versions": [{"version": 1, "parameters": FITTED}]}
        holder.fsrs_params_version = 1
        job.commit()
        finished(thread, outcome)
    state = stored(engine, ready)
    assert state is not None
    assert state.memory == FsrsScheduler(FITTED).review(None, PracticeRating.GOOD, day(0))
