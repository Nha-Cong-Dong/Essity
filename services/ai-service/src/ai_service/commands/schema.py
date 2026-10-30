"""The command bar's contract (T9.1, ADR-0030, US-18): request, fixed operation union, response.

`Command` is the whole vocabulary of the command bar. What is not a member cannot be produced
(AC6): there is no operation that deletes a canonical card, a subject, a document or a question
bank, resets FSRS or history, changes a cost cap or an account. Adding an operation means adding
a model here, its entry in `REFS`, a prompt example, a core service and an `inverse_json`.

The request carries ids and titles only, never document text (AC7). The model sees labels
(`C1`, `S3`, ...), never ids; `REFS` says which fields of an operation are labels the code turns
back into ids.
"""

import datetime
import uuid
from typing import Annotated, Literal, get_args

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

MAX_COMMAND_CHARS = 500
MAX_TITLE_CHARS = 120
MAX_ITEMS = 200
MAX_DOCUMENTS = 50
MAX_TOTAL_TITLE_CHARS = 60_000
MAX_TARGETS = 50
MAX_CONTENT_CHARS = 2000
MAX_DEFER_DAYS = 366


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise ValueError("NUL")
    return text


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("blank")
    return text


Filled = Annotated[str, AfterValidator(_no_nul), AfterValidator(_not_blank)]
Title = Annotated[Filled, Field(max_length=MAX_TITLE_CHARS)]
Content = Annotated[Filled, Field(max_length=MAX_CONTENT_CHARS)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


# --- Request: ids and titles only ----------------------------------------------------------


class ContextItem(_Strict):
    id: uuid.UUID
    title: Title


def _unique_ids(items: list[ContextItem]) -> list[ContextItem]:
    if len({item.id for item in items}) != len(items):
        raise ValueError("duplicate id")
    return items


Items = Annotated[list[ContextItem], Field(max_length=MAX_ITEMS), AfterValidator(_unique_ids)]
Documents = Annotated[
    list[ContextItem], Field(max_length=MAX_DOCUMENTS), AfterValidator(_unique_ids)
]


class ParseCommandRequest(_Strict):
    user_id: uuid.UUID
    subject_id: uuid.UUID
    command: Annotated[Filled, Field(max_length=MAX_COMMAND_CHARS)]
    today: datetime.date
    cards: Items = []
    sections: Items = []
    subjects: Items = []
    question_types: Items = []
    questions: Items = []
    documents: Documents = []

    @model_validator(mode="after")
    def _bounded_context(self) -> "ParseCommandRequest":
        total = sum(
            len(item.title)
            for items in (
                self.cards,
                self.sections,
                self.subjects,
                self.question_types,
                self.questions,
                self.documents,
            )
            for item in items
        )
        if total > MAX_TOTAL_TITLE_CHARS:
            raise ValueError("context too large")
        return self


# --- The fixed operations (ADR-0030 table) --------------------------------------------------

Targets = Annotated[list[uuid.UUID], Field(min_length=1, max_length=MAX_TARGETS)]


class _Op(_Strict):
    pass


class CardEdit(_Op):
    kind: Literal["card_edit"]
    card: uuid.UUID
    text: Content


class CardMerge(_Op):  # drafts only; core refuses a canonical card
    kind: Literal["card_merge"]
    cards: Annotated[list[uuid.UUID], Field(min_length=2, max_length=10)]


class CardSplit(_Op):  # drafts only
    kind: Literal["card_split"]
    card: uuid.UUID
    parts: Annotated[int, Field(ge=2, le=5)]


class CardAdd(_Op):
    kind: Literal["card_add"]
    text: Content
    section: uuid.UUID | None


class CardDiscardDraft(_Op):
    kind: Literal["card_discard_draft"]
    card: uuid.UUID


class CardAddIdea(_Op):  # "thêm ý từ @tài liệu"
    kind: Literal["card_add_idea"]
    card: uuid.UUID
    document: uuid.UUID
    text: Content


class SectionSetPages(_Op):
    kind: Literal["section_set_pages"]
    section: uuid.UUID
    from_page: Annotated[int, Field(ge=1, le=100_000)]
    to_page: Annotated[int, Field(ge=1, le=100_000)]

    @model_validator(mode="after")
    def _ordered(self) -> "SectionSetPages":
        if self.to_page < self.from_page:
            raise ValueError("to_page before from_page")
        return self


class SectionExclude(_Op):
    kind: Literal["section_exclude"]
    sections: Targets


class SectionMark(_Op):
    kind: Literal["section_mark"]
    sections: Targets
    studied: bool


class SuggestOnlySubject(_Op):  # "tuần này chỉ học môn A"
    kind: Literal["suggest_only_subject"]
    subject: uuid.UUID
    until: datetime.date


class SuggestDeferSubject(_Op):  # "để môn B sau ngày 5/11"
    kind: Literal["suggest_defer_subject"]
    subject: uuid.UUID
    until: datetime.date


class QuestionSetType(_Op):
    kind: Literal["question_set_type"]
    question: uuid.UUID
    question_type: uuid.UUID


class QuestionRelink(_Op):  # exactly one target
    kind: Literal["question_relink"]
    question: uuid.UUID
    card: uuid.UUID | None
    section: uuid.UUID | None

    @model_validator(mode="after")
    def _one_target(self) -> "QuestionRelink":
        if (self.card is None) == (self.section is None):
            raise ValueError("exactly one of card, section")
        return self


class QuestionSetAnswer(_Op):
    kind: Literal["question_set_answer"]
    question: uuid.UUID
    text: Content


class QuestionRemoveFromPractice(_Op):
    kind: Literal["question_remove_from_practice"]
    question: uuid.UUID


UnclearReason = Literal["ambiguous", "unknown_target", "unsupported", "missing_info"]


class Unclear(_Op):
    """Never a guess: core shows "Chưa rõ: ..." (or "không làm bằng lệnh" for `unsupported`)."""

    kind: Literal["unclear"]
    reason: UnclearReason


Command = Annotated[
    CardEdit
    | CardMerge
    | CardSplit
    | CardAdd
    | CardDiscardDraft
    | CardAddIdea
    | SectionSetPages
    | SectionExclude
    | SectionMark
    | SuggestOnlySubject
    | SuggestDeferSubject
    | QuestionSetType
    | QuestionRelink
    | QuestionSetAnswer
    | QuestionRemoveFromPractice
    | Unclear,
    Field(discriminator="kind"),
]

OPERATIONS: dict[str, type[_Op]] = {
    get_args(model.model_fields["kind"].annotation)[0]: model
    for model in (
        CardEdit,
        CardMerge,
        CardSplit,
        CardAdd,
        CardDiscardDraft,
        CardAddIdea,
        SectionSetPages,
        SectionExclude,
        SectionMark,
        SuggestOnlySubject,
        SuggestDeferSubject,
        QuestionSetType,
        QuestionRelink,
        QuestionSetAnswer,
        QuestionRemoveFromPractice,
        Unclear,
    )
}

# Which fields of an operation are labels of the context, and of which list. The model writes
# labels; `resolve_labels` turns them into the ids of the request.
LabelKind = Literal["card", "section", "subject", "question_type", "question", "document"]
REFS: dict[str, dict[str, LabelKind]] = {
    "card_edit": {"card": "card"},
    "card_merge": {"cards": "card"},
    "card_split": {"card": "card"},
    "card_add": {"section": "section"},
    "card_discard_draft": {"card": "card"},
    "card_add_idea": {"card": "card", "document": "document"},
    "section_set_pages": {"section": "section"},
    "section_exclude": {"sections": "section"},
    "section_mark": {"sections": "section"},
    "suggest_only_subject": {"subject": "subject"},
    "suggest_defer_subject": {"subject": "subject"},
    "question_set_type": {"question": "question", "question_type": "question_type"},
    "question_relink": {"question": "question", "card": "card", "section": "section"},
    "question_set_answer": {"question": "question"},
    "question_remove_from_practice": {"question": "question"},
    "unclear": {},
}


def check_dates(command: object, today: datetime.date) -> None:
    """A filter ends within `MAX_DEFER_DAYS` from today and not before it."""
    until = getattr(command, "until", None)
    if until is None:
        return
    if until < today or (until - today).days > MAX_DEFER_DAYS:
        raise ValueError("until out of range")


class ParseCommandResponse(_Strict):
    provider: Literal["anthropic", "fake"]
    model: str
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID
    result: Command
