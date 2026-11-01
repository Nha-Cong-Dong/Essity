"""T7.9 (US-02b AC11, AC1, US-06): the review question of a saved card. The AI is a double that
counts its calls (never a real API); the database is real."""

import uuid
from typing import Any

import pytest
from draft_world import World
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.clients.ai_client import NotGraded
from core_api.clients.review_question_contract import ReviewQuestionReply
from core_api.db.models import KnowledgeUnit, Question, QuestionUnit
from core_api.handlers.session_result_v2 import OnSubmissionProcessed
from core_api.handlers.unit_saved import AiUnavailableError, ensure_review_question
from core_api.jobs.regenerate_review_question import REGENERATE_REVIEW_QUESTION
from core_api.repositories.unit import DraftRepository
from fake_storage import FakeStorage

RUN = uuid.uuid4()


def ok(prompt: str = "Câu ôn?") -> ReviewQuestionReply:
    return ReviewQuestionReply(
        status="ok",
        prompt_version="v1",
        run_id=RUN,
        prompt=prompt,
        reference_answer="Đáp án tham chiếu.",
        rubric="Nêu đúng ý chính.",
    )


class FakeAi:
    """Counts calls; answers `reply`, or a numbered question when there is none."""

    def __init__(self, reply: ReviewQuestionReply | NotGraded | None = None) -> None:
        self.reply = reply
        self.payloads: list[dict[str, object]] = []

    def review_question(self, payload: dict[str, object]) -> ReviewQuestionReply | NotGraded:
        self.payloads.append(payload)
        if self.reply is not None:
            return self.reply
        return ok(f"Câu ôn {len(self.payloads)}?")


class Saved:
    def __init__(self, client: TestClient, db: Session, storage: FakeStorage) -> None:
        self.db, self.client = db, client
        self.user, self.headers = signed_in(db)
        self.world = World(db, self.user, storage)
        key = self.world.put([self.world.draft(1), self.world.draft(2)])
        OnSubmissionProcessed(storage)(db, self.world.processed(key))
        db.commit()
        self.base = f"/v1/sessions/{self.world.study.id}/drafts"
        self.cards = client.get(self.base, headers=self.headers).json()["drafts"]
        self.ids = [uuid.UUID(c["id"]) for c in self.cards]

    def save(self) -> Any:
        body = {"units": [{"unit_id": c["id"], "version": c["version"]} for c in self.cards]}
        return self.client.post(f"{self.base}/save", json=body, headers=self.headers)

    def ask(self, unit_id: uuid.UUID, ai: FakeAi, *, lazy: bool = False) -> str:
        return ensure_review_question(self.db, self.user.id, unit_id, ai, lazy=lazy)

    def questions(self, unit_id: uuid.UUID) -> list[Question]:
        return list(
            self.db.scalars(
                select(Question)
                .join(QuestionUnit, QuestionUnit.question_id == Question.id)
                .where(QuestionUnit.unit_id == unit_id)
                .order_by(Question.unit_rev)
            )
        )


@pytest.fixture
def saved(client: TestClient, db_session: Session, fake_storage: FakeStorage) -> Saved:
    return Saved(client, db_session, fake_storage)


def jobs(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = db.execute(
        text("SELECT args FROM procrastinate_jobs WHERE task_name = :k"),
        {"k": REGENERATE_REVIEW_QUESTION},
    )
    return [r[0]["payload"] for r in rows if r[0]["payload"]["user_id"] == str(user_id)]


def test_ac11_save_enqueues_one_job_per_card_and_a_second_save_none(saved: Saved) -> None:
    # Red when: Save does not ask for the questions, or a re-Save asks again.
    assert saved.save().status_code == 200
    first = jobs(saved.db, saved.user.id)
    assert sorted(j["unit_id"] for j in first) == sorted(str(i) for i in saved.ids)
    assert all(j["lazy"] is False and j["user_id"] == str(saved.user.id) for j in first)
    saved.save()
    assert len(jobs(saved.db, saved.user.id)) == 2


def test_ac1_a_draft_has_no_review_question(saved: Saved) -> None:
    # Red when: a card that is not saved gets a question (or a model call).
    ai = FakeAi()
    assert saved.ask(saved.ids[0], ai) == "skipped"
    assert ai.payloads == [] and saved.questions(saved.ids[0]) == []


def test_ac11_save_makes_exactly_one_review_auto_question_with_rubric(saved: Saved) -> None:
    # Red when: no question, a second one, no rubric or answer stored, or no unit_rev / run_id.
    saved.save()
    ai = FakeAi()
    unit_id = saved.ids[0]
    assert saved.ask(unit_id, ai) == "created"
    [question] = saved.questions(unit_id)
    assert (question.source, question.level, question.status) == ("review_auto", 1, "active")
    assert (question.unit_rev, question.run_id) == (1, RUN)
    assert question.rubric == "Nêu đúng ý chính." and question.reference_answer
    assert len(ai.payloads) == 1


def test_ac11_the_card_goes_to_the_model_with_its_text_and_quotes(saved: Saved) -> None:
    saved.save()
    ai = FakeAi()
    saved.ask(saved.ids[0], ai)
    [sent] = ai.payloads
    assert str(sent["title"]).startswith("Thẻ") and sent["quotes"]
    assert sent["user_id"] == str(saved.user.id)


def test_ac11_resave_or_repeated_job_does_not_duplicate_and_calls_nothing(saved: Saved) -> None:
    # Red when: a repeated run (at-least-once delivery, a re-Save) makes a second question or call.
    saved.save()
    ai = FakeAi()
    unit_id = saved.ids[0]
    assert saved.ask(unit_id, ai) == "created"
    assert saved.ask(unit_id, ai) == "current"
    assert saved.ask(unit_id, ai, lazy=True) == "current"
    assert len(saved.questions(unit_id)) == 1 and len(ai.payloads) == 1


def new_rev(saved: Saved, unit_id: uuid.UUID, rev: int) -> None:
    DraftRepository(saved.db, saved.user.id).add_revision(
        unit_id, rev, "user", {"title": "Mới", "summary": "Đã sửa.", "kind": "concept"}
    )
    saved.db.flush()


def test_ac11_edit_keeps_the_old_question_and_makes_the_new_one_lazily(saved: Saved) -> None:
    # Red when: an edit makes a call at once, deletes the old question, or the due card gets none.
    saved.save()
    ai = FakeAi()
    unit_id = saved.ids[0]
    saved.ask(unit_id, ai)
    new_rev(saved, unit_id, 2)
    assert saved.ask(unit_id, ai, lazy=False) == "kept"
    assert len(ai.payloads) == 1 and len(saved.questions(unit_id)) == 1
    assert saved.ask(unit_id, ai, lazy=True) == "created"
    assert [q.unit_rev for q in saved.questions(unit_id)] == [1, 2]
    assert {q.status for q in saved.questions(unit_id)} == {"active"}
    assert saved.ask(unit_id, ai, lazy=True) == "current"
    assert len(ai.payloads) == 2


def test_ac11_cap_reached_is_not_an_error_and_the_old_question_stays(saved: Saved) -> None:
    # Red when: pending_ai raises, or the card loses the question it has.
    saved.save()
    unit_id = saved.ids[0]
    saved.ask(unit_id, FakeAi())
    new_rev(saved, unit_id, 2)
    capped = FakeAi(ReviewQuestionReply(status="pending_ai", prompt_version="v1", run_id=RUN))
    assert saved.ask(unit_id, capped, lazy=True) == "pending_ai"
    assert [q.unit_rev for q in saved.questions(unit_id)] == [1]


def test_ac11_cap_reached_with_no_question_yet_waits_without_error(saved: Saved) -> None:
    saved.save()
    unit_id = saved.ids[0]
    assert saved.ask(unit_id, FakeAi(NotGraded("quota", "quota_hard_cap"))) == "pending_ai"
    assert saved.questions(unit_id) == []
    unit = saved.db.get(KnowledgeUnit, unit_id)
    assert unit is not None and unit.status == "canonical"  # still a card, still in review
    assert saved.ask(unit_id, FakeAi(), lazy=True) == "created"  # a later run makes it


def test_ac11_ai_unreachable_raises_so_the_job_retries(saved: Saved) -> None:
    saved.save()
    with pytest.raises(AiUnavailableError):
        saved.ask(saved.ids[0], FakeAi(NotGraded("unavailable", "timeout")))


def test_ac11_a_broken_reply_makes_no_question(saved: Saved) -> None:
    saved.save()
    bad = FakeAi(
        ReviewQuestionReply(
            status="failed", failure="output_invalid", prompt_version="v1", run_id=RUN
        )
    )
    assert saved.ask(saved.ids[0], bad) == "failed"
    assert saved.questions(saved.ids[0]) == []


def test_ac11_same_wording_is_not_doubled(saved: Saved) -> None:
    # Red when: the unique active hash makes the insert fail, or a second row appears.
    saved.save()
    unit_id = saved.ids[0]
    same = FakeAi(ok("Cùng một câu?"))
    saved.ask(unit_id, same)
    new_rev(saved, unit_id, 2)
    assert saved.ask(unit_id, same, lazy=True) == "created"
    [question] = saved.questions(unit_id)
    assert question.unit_rev == 2


def test_ac11_another_users_card_is_skipped(saved: Saved, db_session: Session) -> None:
    # Red when: a job for another user id reaches this user's card (isolation).
    saved.save()
    ai = FakeAi()
    stranger = uuid.uuid4()
    assert ensure_review_question(db_session, stranger, saved.ids[0], ai, lazy=False) == "skipped"
    assert ai.payloads == []
    assert db_session.scalar(select(func.count()).select_from(Question)) == 0
