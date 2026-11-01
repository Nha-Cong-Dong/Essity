"""T9.6b generated practice questions (US-17 AC1-AC6, AC8). ai-service is a fake that records every
payload and counts the calls: nothing here reaches a model. Rows are written through the models."""

import datetime as dt
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.api.deps import get_now
from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import NotGraded
from core_api.clients.like_contract import DroppedCandidate, KeptCandidate, LikeReply
from core_api.db.models import (
    DocSection,
    Document,
    Question,
    QuestionGeneration,
    QuestionUnit,
    UnitSection,
    User,
)
from core_api.main import app
from core_api.repositories.generated_questions import GeneratedQuestionRepository
from core_api.repositories.stats import StatsRepository
from core_api.security.rate_limit import RateLimitedError, get_rate_limiter
from v2_rows import (
    make_document,
    make_question,
    make_section,
    make_subject,
    make_type,
    make_unit,
)

RUN = uuid.uuid4()
PROMPTS = [
    "Giải thích vì sao bắt tay ba bước cần cả SYN lẫn ACK khi mở kết nối.",
    "So sánh cách TCP và UDP xử lý gói tin bị mất trên đường truyền.",
    "Nêu điều gì xảy ra với cửa sổ nhận khi bộ đệm của máy chủ đầy.",
    "Mô tả vai trò của số thứ tự trong việc sắp xếp lại các đoạn dữ liệu.",
    "Trình bày lý do tiến trình đóng kết nối cần bốn bước thay vì ba.",
]
Headers = dict[str, str]


class FakeLike:
    """Scripted ai-service: by default every card cited, the next unused prompts as candidates."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.script: LikeReply | NotGraded | None = None
        self.prompts = list(PROMPTS)

    def generate_like(self, payload: dict[str, object]) -> LikeReply | NotGraded:
        self.payloads.append(payload)
        if self.script is not None:
            return self.script
        cards: Any = payload["cards"]
        kept = [
            candidate(self.prompts[n], [cards[0]["card_id"]])
            for n in range(min(int(str(payload["count"])), len(self.prompts)))
        ]
        return reply(kept)


def candidate(prompt: str, card_ids: list[str], rubric: str | None = None) -> KeptCandidate:
    return KeptCandidate(
        prompt=prompt,
        reference_answer="Đáp án rút từ thẻ.",
        rubric=rubric or "Nêu được ý chính. Dùng đúng thẻ.",
        card_ids=[uuid.UUID(c) for c in card_ids],
    )


def reply(kept: list[KeptCandidate], status: str = "ok", failure: str | None = None) -> LikeReply:
    return LikeReply(
        status=status,  # type: ignore[arg-type]
        kept=kept,
        dropped=[DroppedCandidate(reason="judge_j3_generic")] if status == "empty" else [],
        failure=failure,
        prompt_version="v1",
        run_id=RUN,
    )


@pytest.fixture(autouse=True)
def frozen_now() -> Iterator[None]:
    app.dependency_overrides[get_now] = lambda: FROZEN_NOW
    yield
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def ai() -> Iterator[FakeLike]:
    fake = FakeLike()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


class World:
    """Alice with one subject: a type, a bank question on two live cards, a draft card that is not
    studied, and an outline leaf with its card."""

    def __init__(self, client: TestClient, session: Session, user: User, headers: Headers) -> None:
        self.client, self.session, self.user, self.headers = client, session, user, headers
        self.subject = make_subject(session, user)
        self.kind = make_type(session, user, self.subject)
        self.u1 = make_unit(session, user, self.subject, title="TCP", summary="Giao thức tin cậy.")
        self.u2 = make_unit(session, user, self.subject, title="UDP", summary="Không bảo đảm.")
        self.draft = make_unit(session, user, self.subject, title="Nháp", status="draft")
        self.bank = make_question(
            session,
            user,
            self.subject,
            n=1,
            prompt="TCP mở kết nối như thế nào và vì sao?",
            source="bank",
            type_id=self.kind.id,
            level=2,
        )
        for unit in (self.u1, self.u2, self.draft):
            session.add(
                QuestionUnit(
                    user_id=user.id,
                    subject_id=self.subject.id,
                    question_id=self.bank.id,
                    unit_id=unit.id,
                )
            )
        session.flush()

    def post(self, body: dict[str, str], subject: uuid.UUID | None = None) -> Any:
        return self.client.post(
            f"/v1/subjects/{subject or self.subject.id}/generated-questions",
            json=body,
            headers=self.headers,
        )

    def on_type(self) -> Any:
        return self.post({"type_id": str(self.kind.id)})

    def stored(self) -> list[Question]:
        return list(
            self.session.scalars(
                select(Question)
                .where(Question.user_id == self.user.id, Question.source == "generated")
                .order_by(Question.created_at, Question.id)
            )
        )

    def leaf(self, *, studied: float = 1.0, excluded: bool = False) -> uuid.UUID:
        document = make_document(self.session, self.user, self.subject, sha="cd" * 32)
        section = make_section(
            self.session, self.user, document, studied_weight=studied, excluded=excluded
        )
        self.session.add(
            UnitSection(
                user_id=self.user.id,
                subject_id=self.subject.id,
                unit_id=self.u2.id,
                section_id=section.id,
            )
        )
        self.session.flush()
        return section.id


@pytest.fixture
def world(client: TestClient, db_session: Session, ai: FakeLike) -> World:
    user, headers = signed_in(db_session)
    return World(client, db_session, user, headers)


def cards_of(payload: dict[str, object]) -> list[dict[str, str]]:
    cards: Any = payload["cards"]
    return cards


# --- AC1, AC4: five per press, only on a press, one call ---------------------------------------


def test_a_press_sends_the_studied_cards_and_stores_five_unkept_candidates(
    world: World, ai: FakeLike
) -> None:
    # US-17 AC1, AC2, AC4, AC5. Red when: a draft card is sent, more or fewer than 5 are asked or
    # stored, a candidate starts kept, or the answer and rubric are not stored at creation.
    response = world.on_type()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok" and len(body["candidates"]) == 5
    assert all(set(c) == {"id", "prompt", "type_id", "label"} for c in body["candidates"])
    [payload] = ai.payloads
    assert payload["count"] == 5 and payload["type_name"] == world.kind.name
    assert {c["card_id"] for c in cards_of(payload)} == {str(world.u1.id), str(world.u2.id)}
    assert payload["samples"] == [{"prompt": world.bank.prompt}]
    rows = world.stored()
    assert len(rows) == 5
    for row in rows:
        assert (row.source, row.quality_status, row.status) == ("generated", "ok", "active")
        assert (row.kept_at, row.answer_origin, row.type_id) == (None, "ai", world.kind.id)
        assert row.answer_text == row.reference_answer and row.rubric == [
            "Nêu được ý chính.",
            "Dùng đúng thẻ.",
        ]
    first_card = uuid.UUID(cards_of(payload)[0]["card_id"])
    for row in rows:
        linked = world.session.scalars(
            select(QuestionUnit.unit_id).where(QuestionUnit.question_id == row.id)
        ).all()
        assert list(linked) == [first_card]


def test_a_second_press_with_candidates_waiting_generates_nothing(
    world: World, ai: FakeLike
) -> None:
    # US-17 AC1 (double click). Red when: two presses call the AI twice or store two sets.
    first = world.on_type().json()
    second = world.on_type().json()
    assert len(ai.payloads) == 1
    assert [c["id"] for c in second["candidates"]] == [c["id"] for c in first["candidates"]]
    assert len(world.stored()) == 5


def test_a_press_while_one_is_running_is_a_neutral_running_answer(
    world: World, ai: FakeLike
) -> None:
    # US-17 AC1. Red when: a second tab pressing mid-generation starts a second AI call.
    GeneratedQuestionRepository(world.session, world.user.id).begin(
        world.subject.id, "type", world.kind.id, FROZEN_NOW
    )
    world.session.flush()
    body = world.on_type().json()
    assert body["status"] == "running" and body["candidates"] == [] and body["message"]
    assert ai.payloads == []


def test_a_running_row_left_by_a_crash_goes_stale(world: World, ai: FakeLike) -> None:
    # US-17 AC1. Red when: one crashed request blocks the button for good.
    repo = GeneratedQuestionRepository(world.session, world.user.id)
    repo.begin(world.subject.id, "type", world.kind.id, FROZEN_NOW - dt.timedelta(minutes=10))
    world.session.flush()
    assert world.on_type().json()["status"] == "ok"
    assert len(ai.payloads) == 1


def test_a_finished_press_leaves_no_running_row(world: World, ai: FakeLike) -> None:
    # Red when: the guard row stays `running` after the set is stored.
    world.on_type()
    states = world.session.scalars(select(QuestionGeneration.status)).all()
    assert list(states) == ["done"]


def test_a_press_on_one_question_uses_it_as_the_only_sample(world: World, ai: FakeLike) -> None:
    # US-17 AC1. Red when: the sample or the cards are not those of the question pressed on.
    assert world.post({"question_id": str(world.bank.id)}).json()["status"] == "ok"
    [payload] = ai.payloads
    assert payload["samples"] == [{"prompt": world.bank.prompt}]
    assert len(cards_of(payload)) == 2


def test_the_request_names_exactly_one_target(world: World, ai: FakeLike) -> None:
    # Red when: no target, or two, is accepted.
    assert world.post({}).status_code == 422
    both = {"type_id": str(world.kind.id), "question_id": str(world.bank.id)}
    assert world.post(both).status_code == 422
    assert ai.payloads == []


# --- AC1: a subject without a bank, per outline leaf --------------------------------------------


def test_a_studied_leaf_generates_with_no_sample_and_the_default_type(
    world: World, ai: FakeLike
) -> None:
    # US-17 AC1 (no bank). Red when: a sample or a type is invented, or the section's cards are
    # not the ones sent.
    section = world.leaf()
    body = world.post({"section_id": str(section)}).json()
    assert body["status"] == "ok"
    [payload] = ai.payloads
    assert payload["samples"] == [] and "type_name" not in payload
    assert [c["card_id"] for c in cards_of(payload)] == [str(world.u2.id)]
    assert {q.type_id for q in world.stored()} == {None}


@pytest.mark.parametrize("kwargs", [{"studied": 0.0}, {"excluded": True}])
def test_an_unstudied_or_excluded_leaf_is_not_found(
    world: World, ai: FakeLike, kwargs: Any
) -> None:
    # US-17 AC1. Red when: "Sinh câu" works for a section the learner has not studied.
    section = world.leaf(**kwargs)
    assert world.post({"section_id": str(section)}).status_code == 404
    assert ai.payloads == []


def test_a_section_with_children_is_not_a_leaf(world: World, ai: FakeLike) -> None:
    # US-17 AC1. Red when: a chapter, not a leaf, can be pressed.
    parent = world.leaf()
    document = world.session.get_one(DocSection, parent).document_id
    make_section(
        world.session,
        world.user,
        world.session.get_one(Document, document),
        parent_id=parent,
        title="Mục con",
    )
    assert world.post({"section_id": str(parent)}).status_code == 404


# --- AC2: only studied cards, only this user's ---------------------------------------------------


def test_no_studied_card_means_no_call(world: World, ai: FakeLike) -> None:
    # US-17 AC2. Red when: the AI is paid for a target with nothing studied.
    world.u1.status = "retired"
    world.u2.skipped_at = FROZEN_NOW
    world.session.flush()
    body = world.on_type().json()
    assert body["status"] == "empty" and body["message"] and ai.payloads == []


def test_a_reply_citing_a_card_that_was_not_sent_is_not_stored(world: World, ai: FakeLike) -> None:
    # US-17 AC2, R03 layer 2. Red when: a candidate citing the draft card (or another user's) is
    # stored because the AI said so.
    ai.script = reply([candidate(PROMPTS[0], [str(world.draft.id)])])
    assert world.on_type().json()["status"] == "empty"
    assert world.stored() == []


def test_a_rubric_that_cannot_be_graded_is_not_stored(world: World, ai: FakeLike) -> None:
    # US-17 AC4. Red when: a candidate whose rubric has an idea longer than the grader accepts is
    # stored (grading would fail closed on it forever).
    long_idea = "Ý " + "dài " * 150 + "."
    ai.script = reply([candidate(PROMPTS[0], [str(world.u1.id)], rubric=long_idea)])
    assert world.on_type().json()["status"] == "empty"


def test_another_users_target_is_not_found(
    world: World, db_session: Session, client: TestClient, ai: FakeLike
) -> None:
    # US-17 §7. Red when: Bob can generate from Alice's type, question or subject.
    bob, bobs = signed_in(db_session)
    bobs_subject = make_subject(db_session, bob)
    url = f"/v1/subjects/{bobs_subject.id}/generated-questions"
    for body in ({"type_id": str(world.kind.id)}, {"question_id": str(world.bank.id)}):
        assert client.post(url, json=body, headers=bobs).status_code == 404
    other = f"/v1/subjects/{world.subject.id}/generated-questions"
    assert client.post(other, json={"type_id": str(world.kind.id)}, headers=bobs).status_code == 404
    assert ai.payloads == []


def test_an_unverified_user_cannot_press(
    client: TestClient, db_session: Session, ai: FakeLike
) -> None:
    # US-17 §7. Red when: a call is paid for an unverified account.
    user, headers = signed_in(db_session, verified=False)
    subject = make_subject(db_session, user)
    response = client.post(
        f"/v1/subjects/{subject.id}/generated-questions",
        json={"type_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert response.status_code in (401, 403) and ai.payloads == []


# --- AC3: near duplicates ------------------------------------------------------------------------


def test_a_candidate_close_to_a_stored_question_is_dropped_by_pg_trgm(
    world: World, ai: FakeLike
) -> None:
    # US-17 AC3. Red when: a one-word variation of a stored question is stored again.
    near = world.bank.prompt.rstrip("?") + " ạ?"
    ai.script = reply(
        [candidate(near, [str(world.u1.id)]), candidate(PROMPTS[1], [str(world.u1.id)])]
    )
    body = world.on_type().json()
    assert [c["prompt"] for c in body["candidates"]] == [PROMPTS[1]]


def test_two_near_identical_candidates_store_one(world: World, ai: FakeLike) -> None:
    # US-17 AC3. Red when: the candidates of one reply are not checked against each other here.
    twin = PROMPTS[0].rstrip(".") + " nhé."
    ai.script = reply(
        [candidate(PROMPTS[0], [str(world.u1.id)]), candidate(twin, [str(world.u1.id)])]
    )
    assert len(world.on_type().json()["candidates"]) == 1


def test_pg_trgm_similarity_is_available(db_session: Session) -> None:
    # Migration 0030. Red when: the extension is not created.
    assert db_session.scalar(text("SELECT similarity('abc def', 'abc def')")) == 1.0


# --- AC5: keep, reject, never again --------------------------------------------------------------


def test_keep_makes_a_practice_question_and_is_idempotent(world: World, ai: FakeLike) -> None:
    # US-17 AC5. Red when: keeping does not set kept_at, moves it on a second call, or the kept
    # question is still listed as waiting.
    first = world.on_type().json()["candidates"][0]["id"]
    url = f"/v1/generated-questions/{first}/keep"
    assert world.client.post(url, headers=world.headers).status_code == 204
    kept_at = world.session.get_one(Question, uuid.UUID(first)).kept_at
    assert kept_at == FROZEN_NOW
    assert world.client.post(url, headers=world.headers).status_code == 204
    assert world.session.get_one(Question, uuid.UUID(first)).kept_at == kept_at
    waiting = world.client.get(
        f"/v1/subjects/{world.subject.id}/generated-questions", headers=world.headers
    ).json()
    assert first not in [c["id"] for c in waiting] and len(waiting) == 4


def test_an_unkept_candidate_is_not_a_practice_question_in_the_stats(
    world: World, ai: FakeLike
) -> None:
    # US-17 AC5. Red when: a candidate nobody kept is counted as a question of the bank.
    world.on_type()
    before = count_bank(world)
    first = world.stored()[0]
    world.client.post(f"/v1/generated-questions/{first.id}/keep", headers=world.headers)
    assert count_bank(world) == before + 1


def count_bank(world: World) -> int:
    bank = StatsRepository(world.session, world.user.id).bank(FROZEN_NOW)
    return sum(len(questions) for questions in bank.values())


def test_reject_retires_it_and_it_is_never_suggested_again(world: World, ai: FakeLike) -> None:
    # US-17 AC5. Red when: a rejected question is asked again, is not in existing_prompts, or
    # can be kept afterwards.
    first = world.on_type().json()["candidates"]
    rejected = first[0]
    url = f"/v1/generated-questions/{rejected['id']}/reject"
    assert world.client.post(url, headers=world.headers).status_code == 204
    assert world.client.post(url, headers=world.headers).status_code == 204  # idempotent
    row = world.session.get_one(Question, uuid.UUID(rejected["id"]))
    assert (row.status, row.quality_status) == ("retired", "rejected")
    keep = f"/v1/generated-questions/{rejected['id']}/keep"
    assert world.client.post(keep, headers=world.headers).status_code == 409
    for c in first[1:]:  # settle the rest, so a new press is a new set
        world.client.post(f"/v1/generated-questions/{c['id']}/reject", headers=world.headers)
    ai.script = reply(
        [
            candidate(rejected["prompt"], [str(world.u1.id)]),
            candidate("Câu mới hoàn toàn khác biệt về nội dung số 9?", [str(world.u1.id)]),
        ]
    )
    body = world.on_type().json()
    assert rejected["prompt"] in ai.payloads[-1]["existing_prompts"]  # type: ignore[operator]
    assert [c["prompt"] for c in body["candidates"]] == [
        "Câu mới hoàn toàn khác biệt về nội dung số 9?"
    ]


def test_a_kept_question_cannot_be_rejected(world: World, ai: FakeLike) -> None:
    # US-17 AC5. Red when: "Không giữ" retires a question the learner already kept.
    first = world.on_type().json()["candidates"][0]["id"]
    world.client.post(f"/v1/generated-questions/{first}/keep", headers=world.headers)
    response = world.client.post(f"/v1/generated-questions/{first}/reject", headers=world.headers)
    assert response.status_code == 409


def test_keep_and_reject_are_the_owners_only(
    world: World, db_session: Session, client: TestClient, ai: FakeLike
) -> None:
    # US-17 §7. Red when: Bob can keep, reject or list Alice's candidates.
    first = world.on_type().json()["candidates"][0]["id"]
    _, bobs = signed_in(db_session)
    for action in ("keep", "reject"):
        assert (
            client.post(f"/v1/generated-questions/{first}/{action}", headers=bobs).status_code
            == 404
        )
    listing = client.get(f"/v1/subjects/{world.subject.id}/generated-questions", headers=bobs)
    assert listing.status_code == 404
    assert world.session.get_one(Question, uuid.UUID(first)).kept_at is None


def test_a_bank_question_cannot_be_kept_or_rejected_here(world: World, ai: FakeLike) -> None:
    # US-17 AC5. Red when: these routes touch a question that is not a generated one.
    for action in ("keep", "reject"):
        url = f"/v1/generated-questions/{world.bank.id}/{action}"
        assert world.client.post(url, headers=world.headers).status_code == 404


# --- AC6, AC8: neutral outcomes, never a retry ---------------------------------------------------


@pytest.mark.parametrize(
    ("script", "status"),
    [
        (reply([], "pending_ai"), "pending_ai"),
        (reply([], "empty", "generation_malformed"), "empty"),
        (NotGraded("unavailable", "timeout"), "pending_ai"),
        (NotGraded("quota", "quota_hard_cap"), "pending_ai"),
        (NotGraded("disabled", "grading_disabled"), "pending_ai"),
        (NotGraded("invalid", "response_schema"), "failed"),
    ],
)
def test_no_set_is_a_neutral_answer_one_call_nothing_stored(
    world: World, ai: FakeLike, script: LikeReply | NotGraded, status: str
) -> None:
    # US-17 AC6, AC8. Red when: the answer is an error status, the call is repeated, anything is
    # stored, or the running row is left behind.
    ai.script = script
    response = world.on_type()
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["candidates"]) == (status, [])
    assert body["message"] and "quota" not in body["message"].lower()
    assert len(ai.payloads) == 1 and world.stored() == []
    assert world.session.scalar(select(func.count()).select_from(QuestionGeneration)) == (
        1 if status == "empty" else 0
    )


def test_nothing_passing_is_empty_and_the_next_press_is_the_learners_own(
    world: World, ai: FakeLike
) -> None:
    # US-17 AC6. Red when: the empty outcome triggers another call by itself.
    ai.script = reply([], "empty")
    assert world.on_type().json()["status"] == "empty"
    assert len(ai.payloads) == 1


def test_out_of_turns_is_pending_ai_without_a_call(world: World, ai: FakeLike) -> None:
    # US-17 AC8. Red when: the rate limit still calls the AI or answers an error.
    class Full:
        def enforce(self, *args: object, **kwargs: object) -> None:
            raise RateLimitedError(1)

    app.dependency_overrides[get_rate_limiter] = lambda: Full()
    try:
        body = world.on_type().json()
    finally:
        app.dependency_overrides.pop(get_rate_limiter, None)
    assert body["status"] == "pending_ai" and body["message"] and ai.payloads == []
    assert world.session.scalar(select(func.count()).select_from(QuestionGeneration)) == 0


# --- Payload limits -------------------------------------------------------------------------------


def test_existing_prompts_are_capped_before_they_are_sent(world: World, ai: FakeLike) -> None:
    # US-17 AC3. Red when: a big bank (or one very long prompt) grows the request without bound.
    for n in range(150):
        make_question(
            world.session, world.user, world.subject, n=100 + n, prompt=f"Câu số {n} " + "x" * 800
        )
    world.on_type()
    existing: Any = ai.payloads[0]["existing_prompts"]
    assert len(existing) <= 100 and all(len(p) <= 300 for p in existing)
    assert sum(len(p) for p in existing) <= 30_000


def test_the_request_carries_no_answer_or_rubric_of_the_samples(world: World, ai: FakeLike) -> None:
    # US-17 §7. Red when: the bank question's answer reaches the AI.
    world.bank.answer_text = "ĐÁP-ÁN-BÍ-MẬT"
    world.bank.answer_origin = "bank"
    world.session.flush()
    world.on_type()
    assert "ĐÁP-ÁN-BÍ-MẬT" not in str(ai.payloads[0])
