"""T8.4 tester: edges the branch tests leave open (US-05 AC11/AC13/AC14, US-16 AC5/AC10).
Each test kills a code change that no other test catches (mutation run, tester.yaml). ai-service is
the scripted fake of `test_t84_practice_api`: nothing here calls a model."""

import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session
from test_t84_practice_api import RUBRIC, FakeAi, Learner, count

from clock import FROZEN_NOW
from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import NotGraded
from core_api.clients.practice_contract import DraftAnswerReply
from core_api.db.models import Grade, PracticeLog, Question, QuestionType
from core_api.main import app
from core_api.repositories.practice_attempt import PracticeAttemptRepository
from core_api.repositories.review import GRADING_LOCK_NAMESPACE
from core_api.security.rate_limit import RateLimitedError, get_rate_limiter
from core_api.services.practice_grading import ensure_reference

Clock = Callable[[datetime], None]


@pytest.fixture
def ai() -> Iterator[FakeAi]:
    fake = FakeAi()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


@pytest.fixture
def learner(client: TestClient, db_session: Session, ai: FakeAi) -> Learner:
    return Learner(client, db_session)


def ratings(session: Session) -> list[int]:
    return list(session.scalars(select(PracticeLog.rating).order_by(PracticeLog.seq)))


def test_tester_rating_uses_the_timing_written_at_submit(
    learner: Learner, db_session: Session, set_now: Clock
) -> None:
    # US-16 AC5 -> practice FSRS (mastery.rating_for). Default reference = 2 ideas x 60 s = 120 s,
    # Easy when the previous attempt was correct and active <= 0.7 x 120 = 84 s and timing_ok.
    # Red when: a correct verdict is not passed as "correct", active time reaches record_grade in
    # ms instead of s, or timing_ok is not the attempt's (a hidden tab still earns Easy).
    question = learner.question()
    set_now(FROZEN_NOW)
    first = learner.open(question)["attempt_id"]
    set_now(FROZEN_NOW + timedelta(seconds=10))
    learner.submit(first)
    second = learner.open(question)["attempt_id"]
    set_now(FROZEN_NOW + timedelta(seconds=20))
    learner.submit(second)
    third = learner.open(question)["attempt_id"]
    set_now(FROZEN_NOW + timedelta(seconds=30))
    learner.submit(third, hidden_ms=1_000)
    assert ratings(db_session) == [3, 4, 3]  # Good, Easy (fast, clean), Good (tab hidden)


def test_tester_partial_idea_is_missing_and_partial_is_hard(learner: Learner, ai: FakeAi) -> None:
    # US-05 AC11 + US-16 (rating_for: partial -> Hard). Red when: an idea judged "partial" is not
    # listed as missing (only "incorrect" ones are), or a partial grade is scheduled as correct.
    ai.verdicts = ["partial", "correct"]
    body = learner.submit(learner.open(learner.question())["attempt_id"])
    assert body["result"]["overall"] == "partial"
    assert body["result"]["missing"] == [RUBRIC[0]]
    assert ratings(learner.session) == [2]


def test_tester_reply_with_another_number_of_ideas_is_invalid_not_500(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC11 (one verdict per rubric idea). Red when: a reply judging fewer ideas than the
    # rubric has is stored as a grade, or crashes the route (zip strict) instead of failing closed.
    ai.verdicts = ["correct"]  # the rubric has two ideas
    body = learner.submit(learner.open(learner.question())["attempt_id"])
    assert (body["grading"], body["failure"], body["result"]) == ("failed", "invalid", None)
    assert count(db_session, Grade) == 0 and count(db_session, PracticeLog) == 0


def test_tester_ai_down_is_pending_and_keeps_the_answer(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14 (neutral copy, "Chấm lại" later). Red when: an outage of ai-service reads as a
    # failed grading instead of pending.
    ai.verdicts = NotGraded("unavailable", "timeout")
    body = learner.submit(learner.open(learner.question())["attempt_id"])
    assert (body["status"], body["grading"]) == ("submitted", "pending")
    assert count(db_session, Grade) == 0


def test_tester_blank_rubric_idea_fails_closed(learner: Learner, ai: FakeAi) -> None:
    # Plan review O3. Red when: a rubric with a blank idea is sent with the idea silently dropped
    # (the overall would be judged on part of the rubric).
    question = learner.question(rubric=["Ba bước", "   "])
    body = learner.submit(learner.open(question)["attempt_id"])
    assert (body["grading"], body["failure"]) == ("failed", "not_ready")
    assert ai.graded == []


def test_tester_question_type_reference_time_decides_timing_ok(
    learner: Learner, db_session: Session, set_now: Clock
) -> None:
    # US-16 AC5: the 3x limit is on the question type's reference time when it has one. Type
    # ref 10 s -> 31 s is slow (default 2 x 60 s would call it ok). Red when: the type is ignored.
    question_id = learner.question()
    kind = QuestionType(
        user_id=learner.user.id,
        subject_id=learner.subject,
        name=f"Định nghĩa {uuid.uuid4().hex[:4]}",
        ref_time_s=10,
        ref_origin="user",
    )
    db_session.add(kind)
    db_session.flush()
    question = db_session.get(Question, question_id)
    assert question is not None
    question.type_id = kind.id
    db_session.flush()
    set_now(FROZEN_NOW)
    attempt = learner.open(question_id)["attempt_id"]
    set_now(FROZEN_NOW + timedelta(seconds=31))
    assert learner.submit(attempt)["timing_ok"] is False


def test_tester_a_worthless_question_is_not_served_again(learner: Learner) -> None:
    # US-16 AC10 ("Câu này vô giá trị"). Red when: a retired question can still be opened and
    # practised (the schedule would restart through a new attempt).
    question = learner.question()
    learner.submit(learner.open(question)["attempt_id"])
    learner.client.post(f"/v1/practice/questions/{question}/worthless", headers=learner.headers)
    response = learner.client.post(
        f"/v1/practice/questions/{question}/open", headers=learner.headers
    )
    assert response.status_code == 404


class Limited:
    """The per-user grading limit is used up."""

    def enforce(self, *_: object) -> None:
        raise RateLimitedError(60)


@pytest.fixture
def limited() -> Iterator[None]:
    app.dependency_overrides[get_rate_limiter] = lambda: Limited()
    yield
    app.dependency_overrides.pop(get_rate_limiter, None)


def test_tester_rate_limit_spends_no_ai_turn_and_keeps_the_answer(
    learner: Learner, db_session: Session, ai: FakeAi, limited: None
) -> None:
    # US-05 AC13/AC14 (AI cap). Red when: the per-user limit is skipped for the draft answer at
    # serve or for the grading at submit (a model call over the cap), or the answer is lost.
    drafted = learner.question(answer_text=None, answer_origin=None)
    learner.open(drafted)
    assert ai.drafted == []
    body = learner.submit(learner.open(learner.question())["attempt_id"])
    assert (body["status"], body["grading"]) == ("submitted", "pending")
    assert body["answer_text"] == "SYN, SYN-ACK, ACK"
    assert ai.graded == [] and count(db_session, Grade) == 0


class FixWhileDrafting(FakeAi):
    """The learner fixes the answer (another request) while the AI is drafting one."""

    def __init__(self, session: Session, question_id: uuid.UUID) -> None:
        super().__init__()
        self.session, self.question_id = session, question_id

    def draft_answer(self, payload: dict[str, object]) -> DraftAnswerReply:
        self.session.execute(
            update(Question)
            .where(Question.id == self.question_id)
            .values(answer_text="Bản của tôi", answer_origin="user")
            .execution_options(synchronize_session=False)
        )
        reply: Any = super().draft_answer(payload)
        return reply


def test_tester_a_fix_made_during_the_draft_is_never_overwritten(
    client: TestClient, db_session: Session
) -> None:
    # US-05 AC13 (the learner's fix is canonical). Red when: the AI draft lands on a question
    # whose answer was written after it was read (the UPDATE must keep `answer_text IS NULL`).
    learner_ = Learner(client, db_session)
    question_id = learner_.question(answer_text=None, answer_origin=None)
    question = db_session.get(Question, question_id)
    assert question is not None and question.answer_text is None
    ai_ = FixWhileDrafting(db_session, question_id)
    assert ensure_reference(db_session, learner_.user.id, question, ai_) is True
    assert len(ai_.drafted) == 1
    assert (question.answer_text, question.answer_origin) == ("Bản của tôi", "user")


def test_tester_a_stale_second_tap_on_the_machine_grade_changes_nothing(
    learner: Learner, db_session: Session
) -> None:
    # US-16 AC10 ("Chấm sai" is one tap). The screen still holds the AI grade's id after the first
    # tap; a second tap with the same verdict must not be a 409 nor a third grade.
    # Red when: the idempotence check only accepts the newest grade's own id.
    attempt = learner.open(learner.question())["attempt_id"]
    machine = learner.submit(attempt)["result"]["grade_id"]
    url = f"/v1/practice/grades/{machine}/override"
    first = learner.client.post(url, json={"verdict": "incorrect"}, headers=learner.headers)
    again = learner.client.post(url, json={"verdict": "incorrect"}, headers=learner.headers)
    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json()["result"]["grade_id"] == first.json()["result"]["grade_id"]
    assert count(db_session, Grade) == 2 and count(db_session, PracticeLog) == 2


def test_tester_regrade_while_another_request_grades_is_in_progress(
    learner: Learner, db_session: Session, ai: FakeAi, engine: Engine
) -> None:
    # T2.13 plan D-2 applied to practice: one grading at a time per attempt. Red when: "Chấm lại"
    # asks the AI (a second paid call, a second grade) while another request holds the lock.
    # The submit goes through the repository: the test session would keep a lock the route took.
    attempt = uuid.UUID(learner.open(learner.question())["attempt_id"])
    PracticeAttemptRepository(db_session, learner.user.id).submit(
        attempt, FROZEN_NOW, hidden_ms=0, reference_seconds=120.0, answer_text="SYN, SYN-ACK, ACK"
    )
    db_session.flush()
    with engine.connect() as other, other.begin():
        key = func.hashtextextended(str(attempt), GRADING_LOCK_NAMESPACE)
        assert other.scalar(select(func.pg_try_advisory_xact_lock(key))) is True
        body = learner.client.post(
            f"/v1/practice/attempts/{attempt}/regrade", headers=learner.headers
        ).json()
    assert body["grading"] == "in_progress"
    assert ai.graded == [] and count(db_session, Grade) == 0
