"""T5.R tester round 2: which level-1 question a due unit is asked when it has several. The ladder
(T5.2) picked the oldest inside a level; T5.R replaces it with a DISTINCT ON subquery whose
ORDER BY keeps that rule. No test held it after test_t52_ladder_selection.py was removed."""

from datetime import timedelta

from sqlalchemy.orm import Session
from test_t28_today_api import RUN, Space

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.today import TodayRepository


# Red when: scheduled_units asks a due unit its newest level-1 question instead of its oldest
# (ORDER BY created_at reversed or dropped). The older question is inserted second, so insertion
# order alone does not make this pass.
def test_t5r_a_due_unit_is_asked_its_oldest_level_1_question(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    unit, newer = space.question(subject, "TCP")
    older = QuestionRepository(db_session, user.id).add_idempotent(
        subject, level=1, prompt="TCP là gì?", reference_answer="a", run_id=RUN
    )
    QuestionUnitRepository(db_session, user.id).link(older.id, unit)
    newer.created_at = FROZEN_NOW - timedelta(days=1)
    older.created_at = FROZEN_NOW - timedelta(days=5)
    space.scheduled(unit, due_in_days=-1)

    due = TodayRepository(db_session, user.id).scheduled_units()
    assert [(u.unit_id, u.question_id) for u in due] == [(unit, older.id)]
