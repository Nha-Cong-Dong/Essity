"""T8.1c (US-14 AC8, AC9): importing a bank again. Questions core already holds are not sent to
the model again; one that lacks a type or sections is asked only for what is missing. The model
is a counting fake: every call is counted, nothing here reaches a paid model."""

import hashlib
import json
import unicodedata
import uuid

from ai_service.tasks.bank_run import KnownIn, PageIn, ParseBankBody, SectionIn, parse_bank
from ai_service.tasks.question_bank import BankPrompt

PAGE = "Câu 1. TCP mở kết nối thế nào?\nCâu 2. UDP có bảo đảm không?\nCâu 3. So sánh TCP và UDP."
SECTION = str(uuid.uuid4())


def core_hash(prompt: str) -> str:
    """The same digest as core_api.domain.question_hash (the two services cannot import each
    other): NFC, whitespace runs made one space, version prefix v1."""
    normalised = " ".join(unicodedata.normalize("NFC", prompt).split())
    return hashlib.sha256(f"v1\n{normalised}".encode()).hexdigest()


class CountingAsk:
    def __init__(self) -> None:
        self.prompts: list[BankPrompt] = []

    def __call__(self, prompt: BankPrompt) -> str:
        self.prompts.append(prompt)
        title = prompt.output_schema.get("title")
        labels = [f"Q{n}" for n in (1, 2, 3)]
        if title == "LlmTypes":
            return json.dumps({"types": [{"name": "Giải thích", "questions": labels}]})
        return json.dumps({"mappings": [{"question": q, "sections": ["S1"]} for q in labels]})


def make_body(known: list[KnownIn]) -> ParseBankBody:
    return ParseBankBody(
        user_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        pages=[PageIn(text=PAGE)],
        sections=[SectionIn(id=SECTION, title="3.1 TCP")],
        known=known,
    )


def done(prompt: str) -> KnownIn:
    return KnownIn(hash=core_hash(prompt), needs_type=False, needs_section=False)


def test_a_bank_already_stored_in_full_makes_no_ai_call() -> None:
    # US-14 AC8. Red when: a re-import of a complete bank still asks the model for types or
    # sections, or the skipped count is wrong.
    ask = CountingAsk()
    known = [
        done(p) for p in ("TCP mở kết nối thế nào?", "UDP có bảo đảm không?", "So sánh TCP và UDP.")
    ]
    result = parse_bank(make_body(known), ask)
    assert ask.prompts == []
    assert (result.status, result.questions, result.skipped) == ("ok", [], 3)


def test_a_question_without_a_type_is_asked_for_its_type_only() -> None:
    # US-14 AC2/AC3, T8.1c. Red when: a missing type is not filled, sections are asked again for
    # a question that has them, or the complete questions are sent back.
    ask = CountingAsk()
    known = [
        done("TCP mở kết nối thế nào?"),
        KnownIn(hash=core_hash("UDP có bảo đảm không?"), needs_type=True, needs_section=False),
        done("So sánh TCP và UDP."),
    ]
    result = parse_bank(make_body(known), ask)
    assert [p.output_schema.get("title") for p in ask.prompts] == ["LlmTypes"]
    assert [(q.ord, q.type_name) for q in result.questions] == [(2, "Giải thích")]
    assert result.questions[0].section_ids == [] and result.skipped == 2


def test_a_question_without_a_section_is_asked_for_its_section_only() -> None:
    ask = CountingAsk()
    known = [
        done("TCP mở kết nối thế nào?"),
        done("UDP có bảo đảm không?"),
        KnownIn(hash=core_hash("So sánh TCP và UDP."), needs_type=False, needs_section=True),
    ]
    result = parse_bank(make_body(known), ask)
    assert [p.output_schema.get("title") for p in ask.prompts] == ["LlmMappings"]
    assert [(q.ord, q.section_ids) for q in result.questions] == [(3, [SECTION])]
    assert result.questions[0].type_name is None


def test_a_new_question_in_a_known_bank_is_fully_processed() -> None:
    ask = CountingAsk()
    known = [done("TCP mở kết nối thế nào?"), done("UDP có bảo đảm không?")]
    result = parse_bank(make_body(known), ask)
    assert len(ask.prompts) == 2  # one types call, one sections call, both for the new question
    assert [q.ord for q in result.questions] == [3] and result.skipped == 2
    assert result.questions[0].type_name == "Giải thích"


def test_nothing_known_behaves_as_before() -> None:
    ask = CountingAsk()
    result = parse_bank(make_body([]), ask)
    assert len(ask.prompts) == 2 and len(result.questions) == 3 and result.skipped == 0
