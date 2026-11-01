"""T8.4 practice routes (US-05 AC9-AC14, US-16 AC5/AC10/AC11; ADR-0029). ai-service is a fake that
records every payload: nothing here calls a model. The setup writes through the repositories."""

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_t28_today_api import Space

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import NotGraded
from core_api.clients.practice_contract import DraftAnswerReply, IdeaResult, PracticeGradeReply
from core_api.db.models import (
    Attempt,
    Grade,
    MemoryState,
    PracticeLog,
    PracticeState,
    Question,
    ReviewLog,
)
from core_api.main import app
from core_api.repositories.practice_attempt import DraftContendedError, PracticeAttemptRepository
from core_api.security.rate_limit import get_rate_limiter
from core_api.services import practice_grading

RUBRIC = ["Ba bước", "Nêu SYN, SYN-ACK, ACK"]
RUN = uuid.uuid4()
Headers = dict[str, str]


class FakeAi:
    """Scripted ai-service: `verdicts` per idea (or a `NotGraded`), `draft` text (or None)."""

    def __init__(self) -> None:
        self.verdicts: list[str] | NotGraded | str = ["correct", "correct"]
        self.draft: str | NotGraded | None = "Đáp án nháp"
        self.graded: list[dict[str, object]] = []
        self.drafted: list[dict[str, object]] = []

    def grade_practice(self, payload: dict[str, object]) -> PracticeGradeReply | NotGraded:
        self.graded.append(payload)
        got = self.verdicts
        if isinstance(got, NotGraded):
            return got
        base: dict[str, Any] = {"prompt_version": "v1", "run_id": RUN}
        if got == "pending":
            return PracticeGradeReply(status="pending_ai", **base)
        assert isinstance(got, list)
        ideas = [IdeaResult(verdict=v, anchor=None) for v in got]  # type: ignore[arg-type]
        overall = (
            "correct"
            if set(got) == {"correct"}
            else "incorrect"
            if set(got) == {"incorrect"}
            else "partial"
        )
        return PracticeGradeReply(status="ok", overall=overall, ideas=ideas, **base)  # type: ignore[arg-type]

    def draft_answer(self, payload: dict[str, object]) -> DraftAnswerReply | NotGraded:
        self.drafted.append(payload)
        if isinstance(self.draft, NotGraded):
            return self.draft
        if self.draft is None:
            return DraftAnswerReply(status="pending_ai", prompt_version="v1", run_id=RUN)
        return DraftAnswerReply(
            status="ok", answer=self.draft, answer_origin="ai", prompt_version="v1", run_id=RUN
        )


class Open:
    """A limiter with turns to spare."""

    def enforce(self, *_: object) -> None:
        return None


@pytest.fixture
def ai() -> Iterator[FakeAi]:
    fake = FakeAi()
    app.dependency_overrides[get_ai_client] = lambda: fake
    # Never the real Redis limiter (fail closed when it is slow): tests that need a limit
    # override it after this fixture (the flaky out-of-turns test, T8.4 review).
    app.dependency_overrides[get_rate_limiter] = lambda: Open()
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)
    app.dependency_overrides.pop(get_rate_limiter, None)


class Learner:
    def __init__(self, client: TestClient, session: Session) -> None:
        self.client, self.session = client, session
        self.user, self.headers = signed_in(session)
        self.space = Space(session, self.user)
        self.subject = self.space.subject()

    def question(self, **fields: Any) -> uuid.UUID:
        _, question = self.space.question(self.subject, f"Câu {uuid.uuid4().hex[:6]}")
        values: dict[str, Any] = {
            "rubric": RUBRIC,
            "answer_text": "Bắt tay ba bước: SYN, SYN-ACK, ACK.",
            "answer_origin": "bank",
            "source": "bank",
        }
        values.update(fields)
        for name, value in values.items():
            setattr(question, name, value)
        self.session.flush()
        return question.id

    def open(self, question_id: uuid.UUID) -> dict[str, Any]:
        response = self.client.post(
            f"/v1/practice/questions/{question_id}/open", headers=self.headers
        )
        assert response.status_code == 200, response.text
        return response.json()

    def submit(
        self, attempt_id: str, text: str = "SYN, SYN-ACK, ACK", **extra: Any
    ) -> dict[str, Any]:
        body = {"answer_text": text, "dont_remember": False, **extra}
        response = self.client.post(
            f"/v1/practice/attempts/{attempt_id}/submit", json=body, headers=self.headers
        )
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def learner(client: TestClient, db_session: Session, ai: FakeAi) -> Learner:
    return Learner(client, db_session)


def count(session: Session, model: Any) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_open_serves_a_draft_with_server_served_at_and_reopen_keeps_it(
    learner: Learner, db_session: Session
) -> None:
    # US-16 AC5. Red when: served_at is written twice, or comes from the client.
    question = learner.question()
    first = learner.open(question)
    served = db_session.get(Attempt, uuid.UUID(first["attempt_id"]))
    assert served is not None and served.served_at == FROZEN_NOW
    assert first["status"] == "draft" and first["result"] is None
    again = learner.open(question)
    assert again["attempt_id"] == first["attempt_id"]
    assert served.served_at == FROZEN_NOW


def test_draft_view_gives_away_nothing(learner: Learner) -> None:
    # US-04 AC1. Red when: opening shows the reference answer or the rubric.
    opened = learner.open(learner.question())
    assert set(opened) == {
        "attempt_id", "status", "grading", "failure", "result", "answer_text",
        "dont_remember", "submitted_at", "timing_ok", "question",
    }  # fmt: skip
    assert "Bắt tay" not in json.dumps(opened) and "Ba bước" not in json.dumps(opened)


def test_submit_grades_by_rubric_and_moves_only_the_practice_schedule(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC9/AC11, US-16 AC11. Red when: payload carries more than the four inputs, overall is
    # not the code's, or a card schedule (review_log, memory_state) changes.
    question = learner.question()
    attempt = learner.open(question)["attempt_id"]
    cards = (count(db_session, ReviewLog), count(db_session, MemoryState))
    body = learner.submit(attempt)
    assert (body["grading"], body["result"]["overall"]) == ("graded", "correct")
    assert body["result"]["reference_answer"].startswith("Bắt tay")
    assert body["result"]["answer_origin"] == "bank"
    [payload] = ai.graded
    assert set(payload) == {
        "user_id", "subject_id", "question", "rubric", "reference_answer", "answer"
    }  # fmt: skip
    assert payload["rubric"] == RUBRIC and payload["answer"] == "SYN, SYN-ACK, ACK"
    assert count(db_session, PracticeLog) == 1 and count(db_session, PracticeState) == 1
    assert (count(db_session, ReviewLog), count(db_session, MemoryState)) == cards
    grade = db_session.scalars(select(Grade)).one()
    assert (grade.source, grade.understanding) == ("ai", None)


def test_partial_and_wrong_follow_the_ideas(learner: Learner, ai: FakeAi) -> None:
    # US-05 AC11. Red when: the missing ideas are not those the model did not credit.
    ai.verdicts = ["correct", "incorrect"]
    body = learner.submit(learner.open(learner.question())["attempt_id"])
    assert body["result"]["overall"] == "partial"
    assert body["result"]["missing"] == [RUBRIC[1]]


def test_regrade_and_double_submit_never_ask_or_schedule_twice(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # T8.3 review: a regrade must not move the schedule twice. Red when: a graded attempt is
    # asked again, or a second log row appears.
    attempt = learner.open(learner.question())["attempt_id"]
    learner.submit(attempt)
    again = learner.client.post(f"/v1/practice/attempts/{attempt}/regrade", headers=learner.headers)
    second = learner.submit(attempt, "một câu khác")
    assert again.json()["grading"] == "graded" and second["grading"] == "graded"
    assert len(ai.graded) == 1
    assert count(db_session, PracticeLog) == 1 and count(db_session, Grade) == 1


def test_timing_formula_hidden_and_slow(
    learner: Learner, db_session: Session, set_now: Callable[[datetime], None]
) -> None:
    # US-16 AC5. Red when: active_ms is not (submit - served_at) - hidden_ms, or hidden time is
    # still timing_ok, or the 3x limit is wrong. Reference = 2 ideas x 60 s by default.
    clean = learner.open(learner.question())["attempt_id"]
    hidden = learner.open(learner.question())["attempt_id"]
    slow = learner.open(learner.question())["attempt_id"]
    set_now(FROZEN_NOW + timedelta(seconds=90))
    assert learner.submit(clean)["timing_ok"] is True
    assert learner.submit(hidden, hidden_ms=20_000)["timing_ok"] is False
    set_now(FROZEN_NOW + timedelta(seconds=361))
    assert learner.submit(slow)["timing_ok"] is False
    rows = {
        str(a.id): a
        for a in db_session.scalars(select(Attempt).where(Attempt.user_id == learner.user.id))
    }
    assert (rows[clean].hidden_ms, rows[clean].active_ms) == (0, 90_000)
    assert (rows[hidden].hidden_ms, rows[hidden].active_ms) == (20_000, 70_000)
    assert rows[slow].active_ms == 361_000


def test_client_cannot_set_served_at_or_extra_fields(learner: Learner) -> None:
    # US-16 AC5. Red when: the body accepts served_at / active_ms from the client.
    attempt = learner.open(learner.question())["attempt_id"]
    for extra in ({"served_at": "2020-01-01T00:00:00Z"}, {"active_ms": 1}, {"timing_ok": True}):
        response = learner.client.post(
            f"/v1/practice/attempts/{attempt}/submit",
            json={"answer_text": "x", "dont_remember": False, **extra},
            headers=learner.headers,
        )
        assert response.status_code == 422


def test_dont_remember_is_graded_by_the_system_without_the_ai(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC2 (shared rule). Red when: "Không nhớ" asks the AI or is not scheduled as wrong.
    attempt = learner.open(learner.question())["attempt_id"]
    body = learner.submit(attempt, "", dont_remember=True)
    assert (body["grading"], body["result"]["overall"]) == ("graded", "forgot")
    assert ai.graded == []
    grade = db_session.scalars(select(Grade)).one()
    assert grade.source == "system"
    assert db_session.scalars(select(PracticeLog.rating)).one() == 1


def test_ai_out_of_turns_saves_the_answer_and_says_pending(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC14. Red when: the answer is lost, a 5xx surfaces, or "Chấm lại" cannot finish it.
    attempt = learner.open(learner.question())["attempt_id"]
    ai.verdicts = NotGraded("quota", "quota_hard_cap")
    body = learner.submit(attempt)
    assert (body["status"], body["grading"], body["result"]) == ("submitted", "pending", None)
    assert body["answer_text"] == "SYN, SYN-ACK, ACK"
    assert count(db_session, Grade) == 0 and count(db_session, PracticeLog) == 0
    ai.verdicts = ["correct", "correct"]
    again = learner.client.post(f"/v1/practice/attempts/{attempt}/regrade", headers=learner.headers)
    assert again.json()["grading"] == "graded"
    ai.verdicts = "pending"


def test_pending_ai_reply_is_pending_too(learner: Learner, ai: FakeAi) -> None:
    ai.verdicts = "pending"
    body = learner.submit(learner.open(learner.question())["attempt_id"])
    assert body["grading"] == "pending"
    read = learner.client.get(
        f"/v1/practice/attempts/{body['attempt_id']}", headers=learner.headers
    )
    assert read.json()["grading"] == "pending"


def test_a_question_without_a_rubric_fails_closed_without_a_call(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # Plan review O3. Red when: a missing rubric reaches the AI, or loses the answer, or 500s.
    attempt = learner.open(learner.question(rubric=None))["attempt_id"]
    body = learner.submit(attempt)
    assert (body["grading"], body["failure"]) == ("failed", "not_ready")
    assert ai.graded == [] and count(db_session, Grade) == 0


def test_string_rubric_is_one_idea(learner: Learner, ai: FakeAi) -> None:
    ai.verdicts = ["correct"]
    body = learner.submit(learner.open(learner.question(rubric="Ý chính"))["attempt_id"])
    assert body["grading"] == "graded" and ai.graded[0]["rubric"] == ["Ý chính"]


def test_override_appends_a_log_row_and_rebuilds_without_touching_cards(
    learner: Learner, db_session: Session
) -> None:
    # US-16 AC10. Red when: the override edits a log row, leaves the old grade effective, or
    # moves review_log / memory_state.
    attempt = learner.open(learner.question())["attempt_id"]
    graded = learner.submit(attempt)
    cards = (count(db_session, ReviewLog), count(db_session, MemoryState))
    response = learner.client.post(
        f"/v1/practice/grades/{graded['result']['grade_id']}/override",
        json={"verdict": "incorrect"},
        headers=learner.headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["overall"] == "incorrect"
    assert count(db_session, PracticeLog) == 2 and count(db_session, Grade) == 2
    ratings = list(db_session.scalars(select(PracticeLog.rating).order_by(PracticeLog.seq)))
    assert ratings[1] == 1  # AGAIN: the override is the verdict the log carries
    assert (count(db_session, ReviewLog), count(db_session, MemoryState)) == cards
    state = db_session.scalars(select(PracticeState)).one()
    assert state.step is not None or state.stability > 0  # rebuilt from the effective log
    same = learner.client.post(
        f"/v1/practice/grades/{response.json()['result']['grade_id']}/override",
        json={"verdict": "incorrect"},
        headers=learner.headers,
    )
    assert same.status_code == 200 and count(db_session, Grade) == 2  # a second tap changes nothing


def test_override_of_an_old_grade_is_refused(learner: Learner) -> None:
    attempt = learner.open(learner.question())["attempt_id"]
    first = learner.submit(attempt)["result"]["grade_id"]
    learner.client.post(
        f"/v1/practice/grades/{first}/override",
        json={"verdict": "incorrect"},
        headers=learner.headers,
    )
    stale = learner.client.post(
        f"/v1/practice/grades/{first}/override",
        json={"verdict": "correct"},
        headers=learner.headers,
    )
    assert stale.status_code == 409


def test_worthless_retires_the_question_and_stops_its_schedule_keeping_the_log(
    learner: Learner, db_session: Session
) -> None:
    # US-16 AC10 / US-09. Red when: the log is deleted, or the schedule keeps running.
    question = learner.question()
    learner.submit(learner.open(question)["attempt_id"])
    response = learner.client.post(
        f"/v1/practice/questions/{question}/worthless", headers=learner.headers
    )
    assert response.status_code == 204
    assert db_session.get(Question, question).status == "retired"  # type: ignore[union-attr]
    assert db_session.scalars(select(PracticeState.removed_at)).one() is not None
    assert count(db_session, PracticeLog) == 1


def test_missing_answer_is_drafted_by_the_ai_once_and_labelled(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC13. Red when: origin is not ai, the question is not ready, or it is drafted twice.
    question = learner.question(answer_text=None, answer_origin=None)
    learner.open(question)
    learner.open(question)
    row = db_session.get(Question, question)
    assert row is not None and (row.answer_text, row.answer_origin) == ("Đáp án nháp", "ai")
    assert len(ai.drafted) == 1
    assert set(ai.drafted[0]) == {"user_id", "subject_id", "question", "cards"}
    body = learner.submit(learner.open(question)["attempt_id"])
    assert body["result"]["answer_origin"] == "ai"
    assert body["result"]["reference_answer"] == "Đáp án nháp"


def test_a_failed_draft_leaves_the_question_usable(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # US-05 AC13/AC14. Red when: a draft failure breaks opening, or half-writes an answer.
    ai.draft = NotGraded("unavailable", "timeout")
    question = learner.question(answer_text=None, answer_origin=None)
    opened = learner.open(question)
    assert opened["status"] == "draft"
    row = db_session.get(Question, question)
    assert row is not None and (row.answer_text, row.answer_origin) == (None, None)
    ai.draft = "Đáp án nháp"
    learner.open(question)  # next serve retries
    assert row.answer_origin == "ai"


def test_a_learners_answer_is_never_overwritten_by_a_draft(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    question = learner.question(answer_text="Bản của tôi", answer_origin="user")
    learner.open(question)
    assert ai.drafted == []
    assert db_session.get(Question, question).answer_text == "Bản của tôi"  # type: ignore[union-attr]


def test_review_auto_question_uses_its_reference_answer(learner: Learner, ai: FakeAi) -> None:
    question = learner.question(answer_text=None, answer_origin=None, source="review_auto")
    body = learner.submit(learner.open(question)["attempt_id"])
    assert body["grading"] == "graded" and ai.drafted == []
    assert ai.graded[0]["reference_answer"] == "a"


def test_other_users_get_404_on_every_route(
    learner: Learner, client: TestClient, db_session: Session
) -> None:
    # ADR-0014. Red when: another user can open, read, save, submit, regrade, override or drop.
    question = learner.question()
    attempt = learner.open(question)["attempt_id"]
    graded = learner.submit(attempt)
    _, bob = signed_in(db_session)
    grade = graded["result"]["grade_id"]
    calls = [
        client.post(f"/v1/practice/questions/{question}/open", headers=bob),
        client.get(f"/v1/practice/attempts/{attempt}", headers=bob),
        client.put(
            f"/v1/practice/attempts/{attempt}/draft",
            json={"answer_text": "x", "dont_remember": False},
            headers=bob,
        ),
        client.post(
            f"/v1/practice/attempts/{attempt}/submit",
            json={"answer_text": "x", "dont_remember": False},
            headers=bob,
        ),
        client.post(f"/v1/practice/attempts/{attempt}/regrade", headers=bob),
        client.post(
            f"/v1/practice/grades/{grade}/override", json={"verdict": "incorrect"}, headers=bob
        ),
        client.post(f"/v1/practice/questions/{question}/worthless", headers=bob),
    ]
    assert [c.status_code for c in calls] == [404] * 7


def test_unverified_user_is_refused(client: TestClient, db_session: Session) -> None:
    # ADR-0001. Red when: a signed-up but unverified account reaches a practice route.
    _, headers = signed_in(db_session, verified=False)
    some = uuid.uuid4()
    assert client.post(f"/v1/practice/questions/{some}/open", headers=headers).status_code == 403
    assert client.post(f"/v1/practice/questions/{some}/open").status_code == 401


def test_empty_answer_is_422_and_nothing_is_submitted(
    learner: Learner, db_session: Session
) -> None:
    attempt = learner.open(learner.question())["attempt_id"]
    response = learner.client.post(
        f"/v1/practice/attempts/{attempt}/submit",
        json={"answer_text": "  ", "dont_remember": False},
        headers=learner.headers,
    )
    assert response.status_code == 422
    row = db_session.get(Attempt, uuid.UUID(attempt))
    assert row is not None and row.status == "draft"


def test_grade_and_schedule_are_one_transaction(
    learner: Learner, db_session: Session, ai: FakeAi, monkeypatch: pytest.MonkeyPatch
) -> None:
    # T8.3 review F3/Y4. Red when: a Grade can outlive a failed record_grade (a grade with no
    # practice_log row would be graded but never scheduled).
    ai.verdicts = NotGraded("unavailable", "timeout")
    attempt = learner.submit(learner.open(learner.question())["attempt_id"])["attempt_id"]
    ai.verdicts = ["correct", "correct"]

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("log write failed")

    monkeypatch.setattr(practice_grading, "record_grade", boom)
    with pytest.raises(RuntimeError), db_session.begin_nested():
        practice_grading.grade_practice_attempt(
            db_session, learner.user.id, uuid.UUID(attempt), ai, may_call_ai=lambda: True
        )
    assert count(db_session, Grade) == 0 and count(db_session, PracticeLog) == 0


def test_export_skips_practice_attempts_and_stats_counts_them(
    learner: Learner, db_session: Session, tmp_path: Path
) -> None:
    # Plan decision (stats keeps, export drops). Red when: a practice attempt reaches the eval
    # export (its grade has no units or anchors to label), or leaves the activity stats.
    from core_api.cli_export_eval import export_rows
    from core_api.repositories.stats import StatsRepository

    learner.user.eval_consent_at = FROZEN_NOW
    learner.submit(learner.open(learner.question())["attempt_id"])
    db_session.flush()
    assert list(export_rows(db_session)) == []
    events = StatsRepository(db_session, learner.user.id).events()
    assert sum(e.questions_answered for e in events) == 1


def test_limits_are_checked_in_core_without_a_call(
    learner: Learner, db_session: Session, ai: FakeAi
) -> None:
    # Review T5. Red when: a too-long reference/rubric reaches ai-service (a 422 forever), or a
    # rubric of more than 8 ideas is cut, or a too-long answer is not told to the learner.
    for fields in (
        {"answer_text": "x" * 1501},
        {"rubric": [f"ý {n}" for n in range(9)]},
        {"rubric": ["y" * 401]},
    ):
        body = learner.submit(learner.open(learner.question(**fields))["attempt_id"])
        assert (body["grading"], body["failure"]) == ("failed", "not_ready")
    assert ai.graded == []
    attempt = learner.open(learner.question())["attempt_id"]
    response = learner.client.post(
        f"/v1/practice/attempts/{attempt}/submit",
        json={"answer_text": "z" * 4001, "dont_remember": False},
        headers=learner.headers,
    )
    assert response.status_code == 422  # schema cap 4000
    assert count(db_session, Grade) == 0


def test_open_answers_409_try_again_when_the_draft_stays_contended(
    learner: Learner, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review F3. Red when: DraftContendedError escapes as a 500 or loses its "try_again" code.
    question = learner.question()

    def contended(self: object, question_id: uuid.UUID, now: object) -> None:
        raise DraftContendedError(question_id)

    monkeypatch.setattr(PracticeAttemptRepository, "open_draft", contended)
    response = learner.client.post(
        f"/v1/practice/questions/{question}/open", headers=learner.headers
    )
    assert (response.status_code, response.json()["detail"]) == (409, "try_again")
