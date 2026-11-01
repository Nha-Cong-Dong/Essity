"""T8.1b pure rules (US-14 AC1, AC2, AC8) and core's call to ai-service's parse-question-bank."""

import uuid

import httpx2
import pytest

from core_api.clients.ai_client import AiServiceClient, NotGraded
from core_api.clients.bank_contract import BankQuestion, BankReply
from core_api.domain.question_bank import (
    NO_ANSWER_LINE,
    default_ref_time_s,
    new_questions,
    reference_answer_of,
    type_name_of,
)
from core_api.domain.question_hash import content_hash

BASE = {"prompt_version": "v1", "run_id": str(uuid.uuid4()), "llm_call_id": None}
QUESTION = {"ord": 1, "prompt": "TCP là gì?", "source_page": 1}


def bq(n: int, prompt: str, answer: str | None = None) -> BankQuestion:
    return BankQuestion(ord=n, prompt=prompt, answer_text=answer, source_page=1)


def test_default_reference_time_is_60_seconds_per_rubric_idea() -> None:
    # US-14 AC2 (T8.1: 60 s x ideas). Red when: the constant or the one-idea floor changes.
    assert [default_ref_time_s(), default_ref_time_s(0), default_ref_time_s(3)] == [60, 60, 180]


def test_a_missing_answer_gets_the_placeholder_and_a_real_one_is_kept_as_is() -> None:
    # US-14 AC1. Red when: the bank's answer is altered or a blank one counts as an answer.
    assert reference_answer_of(None) == NO_ANSWER_LINE == reference_answer_of("  ")
    assert reference_answer_of("Bằng bắt tay ba bước.") == "Bằng bắt tay ba bước."


def test_type_names_are_one_short_line() -> None:
    # US-14 AC2. Red when: a name with a line break or over 100 characters reaches the database.
    assert type_name_of(" So  sánh\nhai giao thức ") == "So sánh hai giao thức"
    assert type_name_of("x" * 300) == "x" * 100
    assert type_name_of("  ") is None and type_name_of(None) is None


def test_new_questions_skips_stored_and_repeated_prompts_and_keeps_bank_order() -> None:
    # US-14 AC8. Red when: a stored hash or an in-file repeat is returned, or the order is lost.
    stored = {content_hash("Đã có rồi?")}
    fresh, duplicates = new_questions(
        [bq(3, "Câu ba?"), bq(1, "Đã  có   rồi?"), bq(2, "Câu hai?"), bq(4, "Câu ba?")], stored
    )
    assert [q.prompt for q in fresh] == ["Câu hai?", "Câu ba?"] and duplicates == 2
    assert fresh[0].content_hash == content_hash("Câu hai?")


def test_a_blank_answer_becomes_none_and_a_real_one_is_not_edited() -> None:
    # US-14 AC1. Red when: whitespace counts as the bank's answer, or the answer is trimmed.
    fresh, _ = new_questions([bq(1, "A?", "  "), bq(2, "B?", " Đáp án B. ")], set())
    assert [q.answer_text for q in fresh] == [None, " Đáp án B. "]


def client_answering(answer: httpx2.Response | Exception) -> tuple[AiServiceClient, list[str]]:
    paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        paths.append(request.url.path)
        if isinstance(answer, Exception):
            raise answer
        return answer

    http = httpx2.Client(
        base_url="http://ai", timeout=10.0, transport=httpx2.MockTransport(handler)
    )
    return AiServiceClient(http), paths


def test_parse_question_bank_parses_the_reply_in_one_call() -> None:
    # Red when: the strict contract rejects what ai-service sends, the path is wrong, or a second
    # call is made.
    body = {**BASE, "status": "ok", "questions": [QUESTION], "unmapped": [1], "reasons": []}
    client, paths = client_answering(httpx2.Response(200, json=body))
    reply = client.parse_question_bank({"pages": []})
    assert isinstance(reply, BankReply) and reply.questions[0].prompt == "TCP là gì?"
    assert paths == ["/v1/parse-question-bank"]


@pytest.mark.parametrize(
    "body",
    [
        {**BASE, "status": "ok", "questions": [{**QUESTION, "extra": 1}]},
        {**BASE, "status": "ok", "questions": [{**QUESTION, "prompt": "x" * 4001}]},
        {**BASE, "status": "ok", "questions": [{**QUESTION, "ord": 0}]},
        {**BASE, "status": "ok", "questions": [{**QUESTION, "section_ids": ["a"] * 6}]},
        {**BASE, "status": "maybe"},
    ],
)
def test_a_reply_outside_the_contract_is_not_trusted(body: dict[str, object]) -> None:
    # R03 layer 2. Red when: an extra field, an oversize text or an unknown status is accepted.
    client, _ = client_answering(httpx2.Response(200, json=body))
    reply = client.parse_question_bank({})
    assert isinstance(reply, NotGraded) and reply.reason == "response_schema"


def test_failures_are_stable_codes_and_never_leak_the_body() -> None:
    # ADR-0013. Red when: ai-service's body reaches the reason, or a timeout raises.
    client, _ = client_answering(httpx2.Response(503, json={"code": "x", "echo": "SECRET"}))
    reply = client.parse_question_bank({})
    assert isinstance(reply, NotGraded) and "SECRET" not in repr(reply)
    client, _ = client_answering(httpx2.ReadTimeout("slow"))
    slow = client.parse_question_bank({})
    assert isinstance(slow, NotGraded) and slow.failure == "unavailable"
