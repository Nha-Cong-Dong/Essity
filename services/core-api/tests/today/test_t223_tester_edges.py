"""T2.23 and T2.18 tester: edges the earlier tests let through (tester.detail.md, PR-F): what the
exam quota counts (`unasked_by_subject`), a question linked to no unit, a skip with a session id
whose unit is outside the session or in two of its questions, and an override of a stale grade."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t28_today_api import RUN
from test_t29_review_sessions_api import ready, start
from test_t213_attempts_api import opened, submit
from test_t218_override_api import grade_id_of, override
from test_t223_skip_api import more_questions, skip, total_items, unit_of

from clock import FROZEN_NOW
from core_api.db.models import Grade
from core_api.domain.scheduling.rating import Verdict
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import GradeRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.today import TodayRepository
from core_api.repositories.unit import KnowledgeUnitRepository


# US-06 AC6, plan b2 ("chưa_hỏi = mảnh active, chưa skipped, chưa có memory_state, môn hiện").
# Red when: a skipped unit, or a unit of a deleted subject, still counts in the exam quota and
# the backlog note.
def test_t223_units_never_asked_leave_out_skipped_units_and_deleted_subjects(
    db_session: Session,
) -> None:
    space, _, _ = ready(db_session, 3)
    subject = SubjectRepository(db_session, space.user.id).list()[0].id
    gone = space.subject("Đã xóa")
    space.question(gone, "Bỏ môn")
    reads = TodayRepository(db_session, space.user.id)
    assert reads.unasked_by_subject() == {subject: 3, gone: 1}
    (unit, *_) = [u.id for u in KnowledgeUnitRepository(db_session, space.user.id).list()]
    KnowledgeUnitRepository(db_session, space.user.id).skip(unit, FROZEN_NOW)
    SubjectRepository(db_session, space.user.id).soft_delete(gone, FROZEN_NOW)
    db_session.flush()
    counts = reads.unasked_by_subject()
    assert sum(counts.values()) == 2 and gone not in counts


# T2.23 new_questions ("câu không gắn mảnh nào vẫn tính là mới", as before T2.23). Red when: a
# question linked to no unit stops being offered as new.
def test_t223_a_question_linked_to_no_unit_is_still_new(db_session: Session) -> None:
    space, _, _ = ready(db_session, 1)
    subject = SubjectRepository(db_session, space.user.id).list()[0].id
    alone = QuestionRepository(db_session, space.user.id).add_idempotent(
        subject, level=1, prompt="Không gắn mảnh?", reference_answer="a", run_id=RUN
    )
    db_session.flush()
    fresh = TodayRepository(db_session, space.user.id).new_questions()
    assert alone.id in {q.question_id for q in fresh}


# US-03 AC8 ("bỏ qua không tính vào trần, phiên vẫn ≤ 20"). Red when: skipping a unit none of
# whose questions is in the session still appends a "replacement", so the session grows.
def test_t223_skipping_a_unit_outside_the_session_adds_nothing_to_it(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _ = ready(db_session, 2)
    session = start(client, headers).json()
    assert session["total"] == 2
    more_questions(db_session, space, 2)  # added after the start: outside the session
    inside = _session_questions(db_session, session["id"])
    outside = next(
        q.id for q in QuestionRepository(db_session, space.user.id).list() if q.id not in inside
    )
    response = skip(client, headers, unit_of(db_session, space, outside), session["id"])
    assert response.status_code == 200 and response.json()["next"]["total"] == 2
    assert total_items(db_session, session["id"]) == 2


# US-03 AC8, "câu nhiều mảnh" / a unit asked by two questions. Red when: a skip that takes two
# questions out of the session brings only one replacement.
def test_t223_a_unit_in_two_questions_of_the_session_brings_two_replacements(
    client: TestClient, db_session: Session
) -> None:
    space, headers, ids = ready(db_session, 2)
    first_unit = unit_of(db_session, space, ids[0])
    QuestionUnitRepository(db_session, space.user.id).link(ids[1], first_unit)
    db_session.flush()
    session = start(client, headers).json()
    assert _session_questions(db_session, session["id"]) == {ids[0], ids[1]}
    more_questions(db_session, space, 3)  # what can take their places
    body = skip(client, headers, first_unit, session["id"]).json()
    assert body["next"]["total"] == 2
    assert total_items(db_session, session["id"]) == 4
    assert body["next"]["question"]["id"] not in {str(ids[0]), str(ids[1])}


# T2.18 "only the current grade". Red when: a stale grade is accepted because the newer grade
# (not an override) happens to have the verdict asked for.
def test_t218_a_stale_grade_with_the_same_verdict_as_a_newer_machine_grade_is_409(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _, attempt_id = opened(client, db_session)
    submit(client, headers, attempt_id)
    stale = db_session.get(Grade, uuid.UUID(grade_id_of(db_session, attempt_id)))
    assert stale is not None
    grades = GradeRepository(db_session, space.user.id)
    units = grades.unit_verdicts(stale.id)
    newer = grades.add_with_units(
        stale.attempt_id,
        source=stale.source,
        overall=Verdict.INCORRECT,
        understanding=None,
        units={unit: Verdict.INCORRECT for unit in units},
        run_id=None,
    )
    db_session.flush()
    assert newer.source != "user_override"
    response = override(client, headers, str(stale.id), "incorrect")
    assert response.status_code == 409 and response.json()["detail"] == "grade_not_current"


def _session_questions(db_session: Session, session_id: str) -> set[uuid.UUID]:
    from core_api.db.models import ReviewSessionItem

    return set(
        db_session.scalars(
            select(ReviewSessionItem.question_id).where(
                ReviewSessionItem.review_session_id == uuid.UUID(session_id)
            )
        )
    )
