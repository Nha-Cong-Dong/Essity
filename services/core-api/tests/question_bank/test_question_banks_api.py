"""T8.1b question bank import (US-14 AC1-AC3, AC8, AC9, section 7). ai-service is a fake that
records every payload and counts the calls: nothing here reaches a model. Rows are written
through the models; the page text comes from a storage double."""

import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import NotGraded
from core_api.clients.bank_contract import BankQuestion, BankReply
from core_api.db.models import (
    DocSection,
    Document,
    Question,
    QuestionSection,
    QuestionType,
    User,
)
from core_api.domain.question_hash import content_hash
from core_api.main import app
from core_api.security.rate_limit import RateLimitedError, get_rate_limiter
from fake_storage import FakeStorage
from v2_rows import NOW, make_document, make_question, make_section, make_subject

RUN = uuid.uuid4()
PAGES_KEY = "users/x/derived/p/pages.json"
Headers = dict[str, str]


def indexed_fields(status: str = "indexed") -> dict[str, Any]:
    """What the database requires of a document in each state (indexed_iff_derived)."""
    if status != "indexed":
        return {"status": status}
    return {
        "status": "indexed",
        "uploaded_at": NOW,
        "run_id": RUN,
        "page_count": 1,
        "toc_key": "d/toc.json",
        "page_labels_key": "d/labels.json",
        "page_text_key": PAGES_KEY,
        "thumbnails_prefix": "d/thumbs",
    }


def bq(n: int, prompt: str, answer: str | None = None, **kw: Any) -> BankQuestion:
    return BankQuestion(ord=n, prompt=prompt, answer_text=answer, source_page=1, **kw)


def reply(questions: list[BankQuestion], status: str = "ok") -> BankReply:
    return BankReply(
        status=status,  # type: ignore[arg-type]
        questions=questions,
        reasons=[],
        prompt_version="v1",
        run_id=RUN,
    )


class FakeBank:
    """Scripted ai-service: `script` is the reply, or a function of the payload."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.script: BankReply | NotGraded | Callable[[dict[str, Any]], BankReply] | None = None

    def parse_question_bank(self, payload: dict[str, Any]) -> BankReply | NotGraded:
        self.payloads.append(payload)
        script = self.script
        if callable(script):
            return script(payload)
        assert script is not None
        return script


@pytest.fixture
def ai() -> Iterator[FakeBank]:
    fake = FakeBank()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


class World:
    """Alice: a subject, an indexed textbook with two leaf sections, an indexed bank file."""

    def __init__(
        self, client: TestClient, session: Session, user: User, headers: Headers, store: FakeStorage
    ) -> None:
        self.client, self.session, self.user, self.headers = client, session, user, headers
        self.store = store
        self.subject = make_subject(session, user)
        self.textbook = make_document(
            session, self.user, self.subject, sha="cd" * 32, role="textbook", **indexed_fields()
        )
        self.parent = make_section(session, user, self.textbook, title="Chương 3")
        self.leaf_a = make_section(
            session, user, self.textbook, title="3.1 TCP", parent_id=self.parent.id, ord=0
        )
        self.leaf_b = make_section(
            session, user, self.textbook, title="3.2 UDP", parent_id=self.parent.id, ord=1
        )
        self.bank = self.make_bank()

    def make_bank(self, sha: str = "ef" * 32, **overrides: Any) -> Document:
        values: dict[str, Any] = {
            "role": "question_bank",
            "short_name": "Đề cương",
            **indexed_fields(str(overrides.pop("status", "indexed"))),
        }
        values.update(overrides)
        document = make_document(self.session, self.user, self.subject, sha=sha, **values)
        pages = [{"page": 1, "text": "Câu 1. TCP là gì?", "needs_vision": False}]
        self.store.objects[PAGES_KEY] = (json.dumps({"pages": pages}).encode(), None)
        return document

    def post(self, document: Document | None = None, subject: uuid.UUID | None = None) -> Any:
        document = document or self.bank
        return self.client.post(
            f"/v1/subjects/{subject or self.subject.id}/question-banks/{document.id}/import",
            headers=self.headers,
        )

    def questions(self) -> list[Question]:
        return list(
            self.session.scalars(
                select(Question)
                .where(Question.user_id == self.user.id, Question.source == "bank")
                .order_by(Question.bank_ord)
            )
        )


@pytest.fixture
def store() -> Iterator[FakeStorage]:
    from core_api.api.deps import get_storage

    fake = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def world(client: TestClient, db_session: Session, ai: FakeBank, store: FakeStorage) -> World:
    user, headers = signed_in(db_session)
    return World(client, db_session, user, headers, store)


# --- AC1: stored as the bank wrote it, the bank's answer is the standard ------------------------


def test_questions_are_stored_as_bank_questions_with_the_banks_own_answers(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC1. Red when: a question is not source=bank, an answer is not answer_origin=bank, a
    # missing answer gets an origin or text, or the file and position are not kept.
    ai.script = reply(
        [
            bq(1, "TCP mở kết nối như thế nào?", "Bằng bắt tay ba bước."),
            bq(2, "UDP có bảo đảm không?"),
        ]
    )
    response = world.post()
    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "ok",
        "message": None,
        "added": 2,
        "duplicates": 0,
        "unmapped": 2,
    }
    first, second = world.questions()
    assert (first.prompt, first.answer_text, first.answer_origin) == (
        "TCP mở kết nối như thế nào?",
        "Bằng bắt tay ba bước.",
        "bank",
    )
    assert (second.answer_text, second.answer_origin) == (None, None)
    assert second.reference_answer.strip()
    for row in (first, second):
        assert (row.source, row.status, row.quality_status) == ("bank", "active", "ok")
        assert row.bank_document_id == world.bank.id and row.kept_at is None
        assert row.content_hash == content_hash(row.prompt)
    assert (first.bank_ord, second.bank_ord) == (0, 1)


def test_one_ai_call_for_the_whole_bank_and_the_payload_has_what_it_needs(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC1, cost note. Red when: more than one call is made, pages or leaf sections are not
    # sent, a parent section or another document's role is sent, or a type name is not offered.
    make_type_row(world, "So sánh")
    ai.script = reply([bq(1, "UDP có bảo đảm không?")])
    world.post()
    [payload] = ai.payloads
    assert payload["pages"] == [{"text": "Câu 1. TCP là gì?", "needs_vision": False}]
    assert payload["existing_types"] == ["So sánh"]
    assert [s["title"] for s in payload["sections"]] == ["3.1 TCP", "3.2 UDP"]
    assert {s["id"] for s in payload["sections"]} == {str(world.leaf_a.id), str(world.leaf_b.id)}
    assert payload["user_id"] == str(world.user.id)


def make_type_row(world: World, name: str) -> QuestionType:
    from v2_rows import make_type

    return make_type(world.session, world.user, world.subject, name=name)


# --- AC2: types ---------------------------------------------------------------------------------


def test_a_suggested_type_is_created_with_the_default_time_and_reused_by_name(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC2, T8.1 (60 s x rubric ideas, ref_origin default). Red when: the default is not
    # 60 s, the origin is not `default`, or a known name makes a second type.
    existing = make_type_row(world, "So sánh")
    ai.script = reply(
        [
            bq(1, "So sánh TCP và UDP.", type_name="So sánh"),
            bq(2, "Giải thích bắt tay ba bước.", type_name="Giải thích"),
            bq(3, "Giải thích điều khiển tắc nghẽn.", type_name="Giải thích"),
        ]
    )
    world.post()
    rows = {t.name: t for t in world.session.scalars(select(QuestionType))}
    assert set(rows) == {"So sánh", "Giải thích"}
    assert (rows["Giải thích"].ref_time_s, rows["Giải thích"].ref_origin) == (60, "default")
    assert rows["So sánh"].id == existing.id and rows["So sánh"].ref_time_s == 120
    by_ord = [q.type_id for q in world.questions()]
    assert by_ord == [existing.id, rows["Giải thích"].id, rows["Giải thích"].id]


# --- AC3: sections ------------------------------------------------------------------------------


def test_sections_are_linked_and_a_question_without_one_is_counted_unmapped(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC3. Red when: a link is missing, or an unlinked question is not in `unmapped`.
    ai.script = reply(
        [
            bq(1, "TCP mở kết nối thế nào?", section_ids=[str(world.leaf_a.id)]),
            bq(2, "So sánh TCP và UDP.", section_ids=[str(world.leaf_a.id), str(world.leaf_b.id)]),
            bq(3, "Câu không thuộc mục nào."),
        ]
    )
    body = world.post().json()
    assert (body["added"], body["unmapped"]) == (3, 1)
    links = {
        (q.prompt, tuple(sorted(str(s) for s in sections)))
        for q in world.questions()
        for sections in [
            world.session.scalars(
                select(QuestionSection.section_id).where(QuestionSection.question_id == q.id)
            ).all()
        ]
    }
    assert links == {
        ("TCP mở kết nối thế nào?", (str(world.leaf_a.id),)),
        ("So sánh TCP và UDP.", tuple(sorted((str(world.leaf_a.id), str(world.leaf_b.id))))),
        ("Câu không thuộc mục nào.", ()),
    }


def test_an_invented_or_foreign_section_id_is_dropped(world: World, ai: FakeBank) -> None:
    # R03 layer 2 / US-01 AC9. Red when: a section id core did not send (random, malformed, or a
    # section of another subject) is linked.
    other = make_subject(world.session, world.user, "Môn khác")
    other_doc = make_document(world.session, world.user, other, sha="12" * 32, role="textbook")
    foreign = make_section(world.session, world.user, other_doc, title="Mục môn khác")
    ai.script = reply(
        [
            bq(
                1,
                "Hỏi về mục lạ?",
                section_ids=[
                    str(uuid.uuid4()),
                    "not-a-uuid",
                    str(foreign.id),
                    str(world.parent.id),
                ],
            )
        ]
    )
    assert world.post().json()["unmapped"] == 1
    assert world.session.scalar(select(func.count()).select_from(QuestionSection)) == 0


def test_a_subject_without_an_outline_sends_no_section_and_leaves_every_question_unmapped(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC5. Red when: sections are invented for a subject with no outline.
    world.session.execute(delete(DocSection).where(DocSection.user_id == world.user.id))
    ai.script = reply([bq(1, "TCP là gì và dùng để làm gì?")])
    body = world.post().json()
    assert ai.payloads[0]["sections"] == [] and (body["added"], body["unmapped"]) == (1, 1)


def test_an_excluded_section_is_not_offered(world: World, ai: FakeBank) -> None:
    # US-14 AC3 (PRD 7.2: "không thi"). Red when: an excluded leaf is sent to the model.
    world.leaf_b.excluded = True
    world.session.flush()
    ai.script = reply([bq(1, "TCP là gì và dùng để làm gì?")])
    world.post()
    assert [s["title"] for s in ai.payloads[0]["sections"]] == ["3.1 TCP"]


# --- AC8: importing again -----------------------------------------------------------------------


def test_importing_the_same_bank_twice_adds_nothing(world: World, ai: FakeBank) -> None:
    # US-14 AC8. Red when: the second import changes the question count, or reports them added.
    ai.script = reply([bq(1, "TCP mở kết nối thế nào?"), bq(2, "UDP có bảo đảm không?")])
    world.post()
    second = world.post().json()
    assert (second["added"], second["duplicates"]) == (0, 2)
    assert len(world.questions()) == 2


def test_the_same_text_typed_differently_is_the_same_question(world: World, ai: FakeBank) -> None:
    # US-14 AC8 (hash normalisation) and the regex-split case after a stopped run. Red when: extra
    # whitespace makes a second copy.
    world_q = make_question(
        world.session,
        world.user,
        world.subject,
        n=1,
        prompt="TCP mở kết nối thế nào?",
        source="bank",
        content_hash=content_hash("TCP mở kết nối thế nào?"),
    )
    ai.script = reply([bq(1, "  TCP  mở kết nối\nthế nào?  "), bq(2, "Một câu mới hoàn toàn.")])
    body = world.post().json()
    assert (body["added"], body["duplicates"]) == (1, 1)
    assert world.session.get(Question, world_q.id) is not None


def test_a_repeated_question_inside_one_bank_is_stored_once(world: World, ai: FakeBank) -> None:
    # US-14 AC8. Red when: two equal questions of one file make two rows (unique-index error).
    ai.script = reply([bq(1, "TCP mở kết nối thế nào?"), bq(2, "TCP mở kết nối thế nào?")])
    body = world.post().json()
    assert (body["added"], body["duplicates"]) == (1, 1)


def test_a_retired_question_does_not_block_a_fresh_copy(world: World, ai: FakeBank) -> None:
    # US-14 AC8 (the unique index is on active questions). Red when: a retired question makes the
    # import skip a question the learner can no longer see.
    make_question(
        world.session,
        world.user,
        world.subject,
        n=1,
        prompt="TCP mở kết nối thế nào?",
        source="bank",
        status="retired",
        content_hash=content_hash("TCP mở kết nối thế nào?"),
    )
    ai.script = reply([bq(1, "TCP mở kết nối thế nào?")])
    assert world.post().json()["added"] == 1


def test_two_banks_may_share_a_question_text_only_once_per_subject(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC8. Red when: a second file with an already stored question doubles it.
    ai.script = reply([bq(1, "TCP mở kết nối thế nào?")])
    world.post()
    second_bank = world.make_bank(sha="aa" * 32, short_name="Đề năm trước")
    ai.script = reply([bq(1, "TCP mở kết nối thế nào?"), bq(2, "Câu riêng của đề năm trước.")])
    body = world.post(second_bank).json()
    assert (body["added"], body["duplicates"]) == (1, 1)


# --- AC9: no turn left, partial, failures --------------------------------------------------------


def test_pending_ai_stores_nothing_and_says_so_neutrally(world: World, ai: FakeBank) -> None:
    # US-14 AC9. Red when: a run the quota stopped stores questions (a repeat import could not
    # type them), or the learner gets no line.
    ai.script = reply([], status="pending_ai")
    body = world.post().json()
    assert body["status"] == "pending_ai" and body["message"] and body["added"] == 0
    assert world.questions() == []


def test_the_rate_limit_is_a_pending_ai_answer_without_an_ai_call(
    world: World, ai: FakeBank
) -> None:
    # US-14 AC9. Red when: a learner over the hourly limit still reaches ai-service.
    class Full:
        def enforce(self, *args: object, **kwargs: object) -> None:
            raise RateLimitedError(60)

    app.dependency_overrides[get_rate_limiter] = lambda: Full()
    try:
        body = world.post().json()
    finally:
        app.dependency_overrides.pop(get_rate_limiter, None)
    assert body["status"] == "pending_ai" and ai.payloads == []


@pytest.mark.parametrize(
    ("failure", "expected"), [("invalid", "failed"), ("unavailable", "pending_ai")]
)
def test_an_ai_service_failure_stores_nothing(
    world: World, ai: FakeBank, failure: str, expected: str
) -> None:
    # US-14 AC9. Red when: a failure stores rows or leaks ai-service's body.
    ai.script = NotGraded(failure, "server_error")  # type: ignore[arg-type]
    body = world.post().json()
    assert body["status"] == expected and body["added"] == 0 and world.questions() == []


def test_a_partial_reply_stores_what_was_checked(world: World, ai: FakeBank) -> None:
    # US-14 AC1. Red when: a partial run drops its checked questions, or hides that it was partial.
    ai.script = reply([bq(1, "TCP mở kết nối thế nào?")], status="partial")
    body = world.post().json()
    assert (body["status"], body["added"]) == ("partial", 1)


def test_a_bank_with_no_questions_is_an_empty_answer(world: World, ai: FakeBank) -> None:
    # US-14 section 6. Red when: an empty file is "ok" or errors.
    ai.script = reply([])
    body = world.post().json()
    assert body["status"] == "empty" and body["message"]


# --- Preconditions and isolation ---------------------------------------------------------------


def test_only_a_question_bank_document_that_is_indexed_can_be_imported(
    world: World, ai: FakeBank
) -> None:
    # US-14 section 7 ("chưa xác minh bị từ chối"). Red when: a textbook or an unread file
    # is sent to the model.
    assert world.post(world.textbook).status_code == 409
    unread = world.make_bank(sha="bb" * 32, status="uploaded", uploaded_at=NOW)
    assert world.post(unread).status_code == 409
    assert ai.payloads == []


def test_unknown_subject_or_document_is_404(world: World, ai: FakeBank) -> None:
    # Red when: a made-up id or a document of another subject of the same learner is accepted.
    other = make_subject(world.session, world.user, "Môn khác")
    assert world.post(subject=other.id).status_code == 404
    assert world.post(subject=uuid.uuid4()).status_code == 404
    gone = world.client.post(
        f"/v1/subjects/{world.subject.id}/question-banks/{uuid.uuid4()}/import",
        headers=world.headers,
    )
    assert gone.status_code == 404 and ai.payloads == []


def test_another_learners_bank_is_a_404_and_stores_nothing(
    world: World, db_session: Session, ai: FakeBank
) -> None:
    # US-14 section 7, US-01 AC9. Red when: Bob can import, read or add questions to Alice's bank.
    _, bob_headers = signed_in(db_session)
    response = world.client.post(
        f"/v1/subjects/{world.subject.id}/question-banks/{world.bank.id}/import",
        headers=bob_headers,
    )
    assert response.status_code == 404 and ai.payloads == [] and world.questions() == []


def test_unauthenticated_is_refused(world: World, ai: FakeBank) -> None:
    # Red when: the route is open without a session.
    response = world.client.post(
        f"/v1/subjects/{world.subject.id}/question-banks/{world.bank.id}/import"
    )
    assert response.status_code in (401, 403) and ai.payloads == []


def test_a_broken_or_oversize_page_file_is_refused_before_any_call(
    world: World, ai: FakeBank, store: FakeStorage
) -> None:
    # Red when: a derived file that is not JSON, or is too large for one request, reaches the
    # model or crashes.
    store.objects[PAGES_KEY] = (b"not json", None)
    assert world.post().status_code == 409
    store.objects[PAGES_KEY] = (json.dumps({"pages": []}).encode() + b" " * (7 * 1024 * 1024), None)
    assert world.post().status_code == 413
    store.down = True
    assert world.post().status_code == 503
    assert ai.payloads == []


def test_logs_never_hold_question_text(
    world: World, ai: FakeBank, log_output: Callable[[], str]
) -> None:
    # ADR-0013. Red when: a question or answer reaches a log.
    ai.script = reply([bq(1, "Câu hỏi bí mật số một?", "Đáp án bí mật.")])
    world.post()
    assert "bí mật" not in log_output()
