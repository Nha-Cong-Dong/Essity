# pyright: reportUnusedImport=false
"""T5.9b review F1: a grade and a PATCH that moves the exam date, side by side, must not deadlock.
The PATCH holds the subject and then writes memory_state (KEY SHARE on the user); the grade's user
lock must therefore not be a full UPDATE lock."""

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from test_t213_grading_races import Ready, correct, ready  # noqa: F401  (fixture)

from core_api.db.models import Attempt, Grade, User
from core_api.grading import record_grade
from core_api.repositories.review import MemoryStateRepository
from core_api.repositories.subject import SubjectRepository
from races import finished, in_thread, wait_for_lock


# Red when: record_grade locks the user FOR UPDATE: Postgres kills the grade (DeadlockDetected).
def test_a_grade_and_an_exam_patch_do_not_deadlock(engine: Engine, ready: Ready) -> None:  # noqa: F811
    with Session(engine) as first:
        user = first.get(User, ready.user_id)
        attempt = first.get(Attempt, ready.attempts[0])
        assert user is not None and attempt is not None
        record_grade(first, user, attempt, correct(ready.unit_id))
        first.commit()
    with Session(engine) as patch, Session(engine) as grader:
        SubjectRepository(patch, ready.user_id).get_with_exam(ready.subject_id, lock=True)
        pid = grader.execute(text("SELECT pg_backend_pid()")).scalar_one()
        user = grader.get(User, ready.user_id)
        attempt = grader.get(Attempt, ready.attempts[1])
        assert user is not None and attempt is not None

        def write() -> object:
            grade = record_grade(grader, user, attempt, correct(ready.unit_id))
            grader.commit()
            return grade

        thread, outcome = in_thread(write)
        wait_for_lock(engine, pid, outcome)
        MemoryStateRepository(patch, ready.user_id).rebuild(subject_id=ready.subject_id)
        patch.commit()
        assert isinstance(finished(thread, outcome), Grade)
