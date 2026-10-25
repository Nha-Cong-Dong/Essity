"""T2.13: grading a submitted attempt (plan "Giao dịch và khóa"). The grader is a stub here; the
HTTP leg and its retry table are in tests/test_ai_client_grade.py."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from clock import FROZEN_NOW, spare_day
from core_api.clients.ai_client import Graded, NotGraded
from core_api.clients.grade_contract import GradeResponse
from core_api.db.models import Grade, GradeUnit, ReviewLog, User
from core_api.domain.scheduling.rating import ReviewRating
from core_api.domain.scheduling.replay import replay
from core_api.grading import grade_attempt
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    AttemptRepository,
    MemoryStateRepository,
    ReviewSessionRepository,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import AnchorRepository, KnowledgeUnitRepository

RUN = uuid.uuid4()


@dataclass
class Stub:
    """ai-service as the grader sees it: scripted answers, every payload kept."""

    verdicts: dict[uuid.UUID, str] = field(default_factory=dict[uuid.UUID, str])
    failure: NotGraded | None = None
    provider: str = "anthropic"
    calls: list[Mapping[str, object]] = field(default_factory=list[Mapping[str, object]])

    def grade(self, payload: Mapping[str, object]) -> Graded | NotGraded:
        self.calls.append(payload)
        if self.failure is not None:
            return self.failure
        units = payload["units"]  # type: ignore[index]
        verdicts = [self.verdicts.get(uuid.UUID(u["unit_id"]), "correct") for u in units]  # type: ignore[index]
        overall = (
            "correct"
            if all(v == "correct" for v in verdicts)
            else ("incorrect" if all(v == "incorrect" for v in verdicts) else "partial")
        )
        return Graded(
            GradeResponse.model_validate(
                {
                    "provider": self.provider,
                    "model": "m",
                    "prompt_version": "v1",
                    "run_id": str(uuid.uuid4()),
                    "llm_call_id": str(uuid.uuid4()),
                    "overall": overall,
                    "understanding": None if overall == "incorrect" else 2,
                    "missing": [] if overall == "correct" else ["ý thiếu"],
                    "units": [
                        {"unit_id": u["unit_id"], "verdict": v}  # type: ignore[index]
                        for u, v in zip(units, verdicts, strict=True)  # type: ignore[arg-type]
                    ],
                    "anchors_used": [units[0]["anchors"][0]["anchor_id"]],  # type: ignore[index]
                }
            )
        )


class Desk:
    """One user's subject, a question on `units` units (one anchor each), and submitted answers."""

    def __init__(self, session: Session, user: User, units: int = 1) -> None:
        self.session, self.user = session, user
        self.subject, _ = SubjectRepository(session, user.id).create_with_exam(
            "Mạng", FROZEN_NOW.date() + timedelta(days=60)
        )
        self.question = QuestionRepository(session, user.id).add_idempotent(
            self.subject.id, level=1, prompt="TCP là gì?", reference_answer="Tin cậy", run_id=RUN
        )
        self.units: list[uuid.UUID] = []
        for n in range(units):
            unit = KnowledgeUnitRepository(session, user.id).create(
                self.subject.id, title=f"ý {n}", summary="s", kind="concept", run_id=RUN
            )
            AnchorRepository(session, user.id).create(
                unit.id, source="document", quote_text=f"nguồn {n}", page_no=1, run_id=RUN
            )
            QuestionUnitRepository(session, user.id).link(self.question.id, unit.id)
            self.units.append(unit.id)
        session.flush()

    def submitted(
        self, text: str = "Tin cậy", *, forgot: bool = False, days_ago: int = 0
    ) -> uuid.UUID:
        at = FROZEN_NOW - timedelta(days=days_ago)
        sitting = ReviewSessionRepository(self.session, self.user.id).start(spare_day(), at)
        attempts = AttemptRepository(self.session, self.user.id)
        attempt = attempts.create_draft(sitting.id, self.question.id)
        attempts.save_draft(attempt.id, answer_text=text, dont_remember=forgot)
        attempts.submit(attempt.id, at)
        self.session.flush()
        return attempt.id

    def grade(self, attempt_id: uuid.UUID, stub: Stub, environment: str = "production"):  # noqa: ANN201
        return grade_attempt(self.session, self.user, attempt_id, stub, environment=environment)

    def count(self, model: Any) -> int:
        return self.session.scalar(
            select(func.count()).select_from(model).where(model.user_id == self.user.id)
        )  # type: ignore[attr-defined]


@pytest.fixture
def desk(db_session: Session, two_users: tuple[User, User]) -> Desk:
    return Desk(db_session, two_users[0], units=2)


# T2.13 case 1, US-05 AC9, US-06 AC5. Red when: one of the four tables is not written, or the
# units share one rating.
def test_t213_graded_in_time_writes_grade_units_log_and_state(desk: Desk) -> None:
    attempt = desk.submitted()
    stub = Stub(verdicts={desk.units[1]: "incorrect"})
    outcome = desk.grade(attempt, stub)
    assert outcome.grading == "graded" and outcome.failure is None
    assert (desk.count(Grade), desk.count(GradeUnit), desk.count(ReviewLog)) == (1, 2, 2)
    rows = desk.session.execute(select(ReviewLog.unit_id, ReviewLog.rating)).all()
    ratings = {unit_id: rating for unit_id, rating in rows}
    assert ratings == {desk.units[0]: ReviewRating.GOOD, desk.units[1]: ReviewRating.AGAIN}
    states = MemoryStateRepository(desk.session, desk.user.id)
    assert all(states.state(u) is not None for u in desk.units)
    # US-05 AC8: the request carries every unit's source.
    sent = stub.calls[0]["units"]  # type: ignore[index]
    quotes = {u["anchors"][0]["quote_text"] for u in sent}  # type: ignore[index]
    assert quotes == {"nguồn 0", "nguồn 1"}


# T2.13 case 2. Red when: a failed grading writes a grade or loses the answer.
def test_t213_a_failure_writes_no_grade_and_keeps_the_answer(desk: Desk) -> None:
    attempt = desk.submitted("Câu của tôi")
    outcome = desk.grade(attempt, Stub(failure=NotGraded("unavailable", "timeout")))
    assert (outcome.grading, outcome.failure) == ("failed", "unavailable")
    assert desk.count(Grade) == 0
    kept = AttemptRepository(desk.session, desk.user.id).get(attempt)
    assert kept is not None and (kept.status, kept.answer_text) == ("submitted", "Câu của tôi")


# T2.13 case 4. Red when: a write failing half-way leaves part of the grade behind.
def test_t213_failure_mid_transaction_leaves_no_grade(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempt = desk.submitted()

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(MemoryStateRepository, "upsert", broken)
    outcome = desk.grade(attempt, Stub())
    assert outcome.grading == "failed"
    assert (desk.count(Grade), desk.count(GradeUnit), desk.count(ReviewLog)) == (0, 0, 0)


# US-04 AC2. Red when: "Không nhớ" calls the AI or is not rated Again.
def test_us04_ac2_dont_remember_is_system_forgot_again_without_ai(desk: Desk) -> None:
    attempt = desk.submitted("", forgot=True)
    stub = Stub()
    outcome = desk.grade(attempt, stub)
    assert outcome.grading == "graded" and stub.calls == []
    grade = desk.session.scalars(select(Grade)).one()
    assert (grade.source, grade.overall) == ("system", "forgot")
    assert set(desk.session.scalars(select(ReviewLog.rating))) == {ReviewRating.AGAIN}


# R41 layer 2. Red when: the fake grader's answer is stored in production.
def test_r41_fake_answer_in_production_writes_nothing(
    desk: Desk, caplog: pytest.LogCaptureFixture
) -> None:
    attempt = desk.submitted()
    with caplog.at_level("ERROR", logger="core_api.grading"):
        outcome = desk.grade(attempt, Stub(provider="fake"), environment="production")
    assert (outcome.grading, outcome.failure) == ("failed", "invalid")
    assert desk.count(Grade) == 0
    assert [r.levelname for r in caplog.records if r.message == "grade refused"] == ["ERROR"]
    local = desk.grade(desk.submitted(), Stub(provider="fake"), environment="local")
    assert local.grading == "graded" and local.grade is not None and local.grade.source == "fake"


# Plan D-6. Red when: a question with a unit lacking a source is sent to the AI.
def test_t213_a_request_outside_the_limits_is_invalid_without_ai(desk: Desk) -> None:
    lonely = KnowledgeUnitRepository(desk.session, desk.user.id).create(
        desk.subject.id, title="không nguồn", summary="s", kind="concept", run_id=RUN
    )
    QuestionUnitRepository(desk.session, desk.user.id).link(desk.question.id, lonely.id)
    stub = Stub()
    outcome = desk.grade(desk.submitted(), stub)
    assert (outcome.grading, outcome.failure, stub.calls) == ("failed", "invalid", [])


# "Chấm lại" when a grade exists. Red when: the AI is paid a second time for a graded answer.
def test_t213_a_graded_attempt_is_not_graded_again(desk: Desk) -> None:
    attempt = desk.submitted()
    stub = Stub()
    first = desk.grade(attempt, stub)
    again = desk.grade(attempt, stub)
    assert len(stub.calls) == 1
    assert again.grade is not None and first.grade is not None and again.grade.id == first.grade.id


# PLAN T2.13 25/10. Red when: an answer graded late (older than the last review) is applied as one
# more step, so the cache differs from the history replayed in order.
def test_t213_grading_an_older_attempt_replays_the_unit(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    desk = Desk(db_session, two_users[0], units=1)
    older = desk.submitted(days_ago=6)
    newer = desk.submitted(days_ago=1)
    desk.grade(newer, Stub())
    desk.grade(older, Stub(verdicts={desk.units[0]: "incorrect"}))
    unit = desk.units[0]
    logs = db_session.execute(
        select(ReviewLog.rating, ReviewLog.reviewed_at)
        .where(ReviewLog.unit_id == unit)
        .order_by(ReviewLog.reviewed_at)
    ).all()
    found = SubjectRepository(db_session, desk.user.id).get_with_exam(desk.subject.id)
    assert found is not None
    exam = found[1].exam_date
    expected = replay(
        [(ReviewRating(r), at) for r, at in logs],
        exam_day=exam,
        tz=ZoneInfo(desk.user.timezone),
        day_start_hour=desk.user.day_start_hour,
    )
    assert MemoryStateRepository(db_session, desk.user.id).state(unit) == expected
