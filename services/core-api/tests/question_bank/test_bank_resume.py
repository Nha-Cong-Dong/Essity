# ruff: noqa: F811
# pyright: reportUnusedImport=false
"""T8.1c (US-14 AC8, AC9): an import stopped for lack of an AI turn is queued and runs by itself
when turns return; importing again skips what is complete and fills what was saved without a type
or section. ai-service and the limiter are fakes that count every call; nothing reaches a model."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session
from test_question_banks_api import (  # noqa: F401
    FakeBank,
    World,
    ai,
    bq,
    reply,
    store,
    world,
)

from core_api.clients.ai_client import NotGraded
from core_api.clients.bank_contract import BankReply
from core_api.db.models import DocSection, Question, QuestionSection, User
from core_api.domain.question_hash import content_hash
from core_api.jobs.question_bank_import import MAX_AGE, QUESTION_BANK_IMPORT, run_queued
from core_api.security.rate_limit import RateLimitResult
from v2_rows import make_question, make_type

Q1, Q2 = "TCP mở kết nối thế nào?", "UDP có bảo đảm không?"


def jobs(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        text("SELECT args, status FROM procrastinate_jobs WHERE task_name = :k ORDER BY id"),
        {"k": QUESTION_BANK_IMPORT},
    ).all()
    return [{**row[0]["payload"], "status": row[1]} for row in rows]


class Turns:
    """The per-user limiter: `open` False means no turn. Counts the turns spent."""

    def __init__(self, open: bool = True) -> None:
        self.open = open
        self.spent = 0

    def hit(self, rule: object, key: str) -> RateLimitResult:
        if not self.open:
            return RateLimitResult(allowed=False, retry_after_seconds=60)
        self.spent += 1
        return RateLimitResult(allowed=True, retry_after_seconds=60, redis_key=key)

    def refund(self, hit: RateLimitResult) -> None:
        self.spent -= 1


def stored(world: World, prompt: str, **kw: Any) -> Question:
    return make_question(
        world.session,
        world.user,
        world.subject,
        n=abs(hash(prompt)) % 10_000,
        prompt=prompt,
        source="bank",
        content_hash=content_hash(prompt),
        bank_document_id=world.bank.id,
        **kw,
    )


def link(world: World, question: Question, section_id: uuid.UUID) -> None:
    world.session.add(
        QuestionSection(
            user_id=world.user.id,
            subject_id=world.subject.id,
            question_id=question.id,
            section_id=section_id,
        )
    )
    world.session.flush()


def links_of(world: World, question: Question) -> list[uuid.UUID]:
    return list(
        world.session.scalars(
            select(QuestionSection.section_id).where(QuestionSection.question_id == question.id)
        )
    )


def payload_of(world: World, queued_at: datetime | None = None) -> dict[str, Any]:
    return {
        "user_id": str(world.user.id),
        "subject_id": str(world.subject.id),
        "document_id": str(world.bank.id),
        "queued_at": (queued_at or datetime.now(UTC)).isoformat(),
    }


def run(
    world: World,
    ai: FakeBank,
    turns: Turns | None = None,
    payload: dict[str, Any] | None = None,
    queued_at: datetime | None = None,
) -> str:
    return run_queued(
        world.session,
        payload or payload_of(world, queued_at),
        ai,
        world.store,
        turns or Turns(),
        datetime.now(UTC),
    )


# --- AC9: queued when there is no turn ----------------------------------------------------------


def test_no_turn_queues_the_import_once_and_stores_nothing(world: World, ai: FakeBank) -> None:
    # US-14 AC9. Red when: a stopped import leaves nothing queued, queues the same bank twice, or
    # stores a half-typed bank.
    ai.script = reply([], status="pending_ai")
    first = world.post().json()
    second = world.post().json()
    assert first["status"] == second["status"] == "pending_ai" and first["message"]
    [job] = jobs(world.session)
    assert (job["user_id"], job["document_id"]) == (str(world.user.id), str(world.bank.id))
    assert world.questions() == []


def test_an_ai_outage_is_queued_but_a_bad_file_is_not(world: World, ai: FakeBank) -> None:
    # US-14 AC9. Red when: an unusable file is retried for days, or an outage is dropped.
    ai.script = NotGraded("invalid", "server_error")
    assert world.post().json()["status"] == "failed" and jobs(world.session) == []
    ai.script = NotGraded("unavailable", "server_error")
    assert world.post().json()["status"] == "pending_ai" and len(jobs(world.session)) == 1


def test_the_queued_job_stores_the_bank_when_a_turn_is_back(world: World, ai: FakeBank) -> None:
    # US-14 AC9. Red when: the job does not store the questions, or stores them twice when it
    # runs again (delivery is at least once).
    ai.script = reply([bq(1, Q1), bq(2, Q2)])
    assert run(world, ai) == "done"
    assert run(world, ai) == "done"
    assert [q.prompt for q in world.questions()] == [Q1, Q2]


def test_the_queued_job_waits_again_when_there_is_still_no_turn(world: World, ai: FakeBank) -> None:
    # US-14 AC9. Red when: a job without a turn calls ai-service, stores something, or is lost.
    ai.script = reply([bq(1, Q1)])
    assert run(world, ai, Turns(open=False)) == "requeued"
    assert ai.payloads == [] and world.questions() == []
    assert len(jobs(world.session)) == 1
    ai.script = reply([], status="pending_ai")
    assert run(world, ai) == "requeued"
    assert world.questions() == []


def test_a_job_that_waited_too_long_is_dropped_without_a_call(world: World, ai: FakeBank) -> None:
    # US-14 AC9 (same limit as T8.4b). Red when: an old job keeps spending turns.
    ai.script = reply([bq(1, Q1)])
    old = datetime.now(UTC) - MAX_AGE - timedelta(minutes=1)
    assert run(world, ai, queued_at=old) == "dropped"
    assert ai.payloads == [] and jobs(world.session) == []


def test_a_job_whose_bank_or_account_is_gone_is_dropped(world: World, ai: FakeBank) -> None:
    # US-14 AC9, ADR-0001. Red when: a deleted bank or account keeps being retried.
    ai.script = reply([bq(1, Q1)])
    other = payload_of(world) | {"document_id": str(uuid.uuid4())}
    assert run(world, ai, payload=other) == "dropped"
    user = world.session.get(User, world.user.id)
    assert user is not None
    user.deleted_at = datetime.now(UTC)
    world.session.flush()
    assert run(world, ai) == "dropped"
    assert ai.payloads == []


# --- AC8: importing again -----------------------------------------------------------------------


def test_the_payload_tells_ai_service_what_is_stored_and_what_it_lacks(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC8. Red when: a complete question is reported as lacking, or a lack is not reported.
    kind = make_type(world.session, world.user, world.subject)
    done = stored(world, Q1, type_id=kind.id)
    link(world, done, world.leaf_a.id)
    stored(world, Q2)
    ai.script = reply([])
    world.post()
    known = {k["hash"]: k for k in ai.payloads[0]["known"]}
    assert known[content_hash(Q1)] == {
        "hash": content_hash(Q1),
        "needs_type": False,
        "needs_section": False,
    }
    assert known[content_hash(Q2)]["needs_type"] and known[content_hash(Q2)]["needs_section"]


def test_a_subject_without_sections_never_asks_for_sections(world: World, ai: FakeBank) -> None:
    # US-14 AC5/AC8. Red when: a complete question of an outline-less subject is asked again.
    world.session.execute(delete(DocSection).where(DocSection.user_id == world.user.id))
    kind = make_type(world.session, world.user, world.subject)
    stored(world, Q1, type_id=kind.id)
    ai.script = reply([])
    world.post()
    assert ai.payloads[0]["known"][0]["needs_section"] is False


def test_a_reply_that_skipped_everything_is_ok_not_empty(world: World, ai: FakeBank) -> None:
    # US-14 AC8. Red when: re-importing a complete bank says "no question found".
    stored(world, Q1)
    stored(world, Q2)
    ai.script = BankReply(
        status="ok", questions=[], skipped=2, prompt_version="v1", run_id=uuid.uuid4()
    )
    body = world.post().json()
    assert (body["status"], body["added"], body["duplicates"], body["message"]) == (
        "ok",
        0,
        2,
        None,
    )


def test_a_question_saved_without_type_or_section_is_filled_on_the_next_import(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC2/AC3. Red when: the type or the sections stay empty, or the question is doubled.
    bare = stored(world, Q1)
    ai.script = reply([bq(1, Q1, type_name="Giải thích", section_ids=[str(world.leaf_a.id)])])
    body = world.post().json()
    assert (body["added"], body["duplicates"]) == (0, 1)
    world.session.refresh(bare)
    assert bare.type_id is not None and len(world.questions()) == 1
    assert links_of(world, bare) == [world.leaf_a.id]


def test_a_filled_question_is_never_rewritten(world: World, ai: FakeBank) -> None:
    # US-14 AC1 / principle 8. Red when: a type or section already set is replaced, or the
    # stored answer changes.
    kind = make_type(world.session, world.user, world.subject, name="So sánh")
    done = stored(world, Q1, type_id=kind.id)
    link(world, done, world.leaf_b.id)
    ai.script = reply(
        [bq(1, Q1, "Đáp án mới", type_name="Giải thích", section_ids=[str(world.leaf_a.id)])]
    )
    world.post()
    world.session.refresh(done)
    assert done.type_id == kind.id and done.answer_text is None
    assert links_of(world, done) == [world.leaf_b.id]
    assert world.session.scalar(select(func.count()).select_from(Question)) == 1


def test_retries_while_the_global_quota_is_out_cost_the_learner_no_turn(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC9. Red when: each 10-minute retry of a queued import spends one of the learner's
    # per-minute turns although the AI answered nothing.
    turns = Turns()
    ai.script = NotGraded("quota", "quota_hard_cap")
    for _ in range(5):
        assert run(world, ai, turns) == "requeued"
    assert len(ai.payloads) == 5 and turns.spent == 0
    ai.script = reply([], status="pending_ai")
    assert run(world, ai, turns) == "requeued" and turns.spent == 0
    ai.script = reply([bq(1, Q1)])
    assert run(world, ai, turns) == "done" and turns.spent == 1


def test_one_learners_stored_hashes_are_never_sent_for_another(world: World, ai: FakeBank) -> None:
    # US-14 AC8, US-01 AC9. Red when: the known list of Alice's import holds a hash of Bob's
    # question (same subject id or not), which would leak and skip her questions.
    from accounts import signed_in
    from v2_rows import make_subject

    bob, _ = signed_in(world.session)
    bob_subject = make_subject(world.session, bob)
    make_question(
        world.session,
        bob,
        bob_subject,
        n=77,
        prompt="Câu riêng của Bob?",
        source="bank",
        content_hash=content_hash("Câu riêng của Bob?"),
    )
    stored(world, Q1)
    ai.script = reply([])
    world.post()
    assert [k["hash"] for k in ai.payloads[0]["known"]] == [content_hash(Q1)]
