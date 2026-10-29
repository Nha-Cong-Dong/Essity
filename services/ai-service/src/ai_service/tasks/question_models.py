"""Models of the question-generation core (T4.16a, US-04b level 1 "nhan biet").

The core takes the knowledge units of one session (title, summary, the anchored quotes) and returns
level-1 questions: exactly one unit each, with a reference answer and a rubric. `unit_id` stays on
the code side: the model sees labels `U1`..`Un` only. T4.16b writes the result into the claim-check
file that `session.processed.v1` points at (the event itself carries no questions); T4.17 persists
`question` and `question_unit`.
"""

import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_UNITS = 40
MAX_QUOTES_PER_UNIT = 5
MAX_QUOTE_CHARS = 1000
MAX_TOTAL_CHARS = 100_000
MAX_TITLE_CHARS = 200
MAX_SUMMARY_CHARS = 1000
MAX_PROMPT_CHARS = 500
MAX_REFERENCE_CHARS = 1500
MAX_RUBRIC_CHARS = 1500
MAX_QUESTIONS_PER_UNIT = 2
MAX_QUESTIONS_OUT = MAX_UNITS * MAX_QUESTIONS_PER_UNIT * 2
MAX_OUTPUT_CHARS = 120_000
MAX_LEVEL3_QUESTIONS = MAX_UNITS
MAX_UNITS_PER_QUESTION = 6


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise ValueError("NUL")
    return text


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("blank")
    return text


Text = Annotated[str, AfterValidator(_no_nul)]
Filled = Annotated[str, AfterValidator(_no_nul), AfterValidator(_not_blank)]
Quote = Annotated[Filled, Field(max_length=MAX_QUOTE_CHARS)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class QuestionUnit(_Strict):
    unit_id: uuid.UUID
    title: Annotated[Filled, Field(max_length=MAX_TITLE_CHARS)]
    summary: Annotated[Text, Field(max_length=MAX_SUMMARY_CHARS)]
    quotes: Annotated[list[Quote], Field(max_length=MAX_QUOTES_PER_UNIT)] = []


class QuestionRequest(_Strict):
    units: Annotated[list[QuestionUnit], Field(max_length=MAX_UNITS)]


# --- What the model may say (checked by `check_questions`) ----------------------------------


class LlmQuestion(_Strict):
    unit: str  # "U3"
    prompt: Annotated[Filled, Field(max_length=MAX_PROMPT_CHARS)]
    reference_answer: Annotated[Filled, Field(max_length=MAX_REFERENCE_CHARS)]
    rubric: Annotated[Filled, Field(max_length=MAX_RUBRIC_CHARS)]


class LlmQuestions(_Strict):
    questions: Annotated[list[LlmQuestion], Field(max_length=MAX_QUESTIONS_OUT)]


# --- Result ---------------------------------------------------------------------------------


class GeneratedQuestion(_Strict):
    unit_id: uuid.UUID
    level: Literal[1] = 1
    prompt: str
    reference_answer: str
    rubric: str


class DroppedQuestion(_Strict):
    """A question the code refused. Rule name only: no text from the model or the source."""

    reason: str


class QuestionResult(_Strict):
    questions: list[GeneratedQuestion]
    dropped: list[DroppedQuestion]


# --- Levels 2 and 3 (T5.1) ------------------------------------------------------------------


class LlmHigherQuestion(_Strict):
    level: Literal[2, 3]
    units: Annotated[list[str], Field(min_length=1, max_length=MAX_UNITS_PER_QUESTION)]
    prompt: Annotated[Filled, Field(max_length=MAX_PROMPT_CHARS)]
    reference_answer: Annotated[Filled, Field(max_length=MAX_REFERENCE_CHARS)]
    rubric: Annotated[Filled, Field(max_length=MAX_RUBRIC_CHARS)]


class LlmHigherQuestions(_Strict):
    questions: Annotated[list[LlmHigherQuestion], Field(max_length=MAX_QUESTIONS_OUT)]


class HigherQuestion(_Strict):
    """Level 2 covers 1-2 units, level 3 at least 2 (US-04b AC1). Ids stay on the code side."""

    level: Literal[2, 3]
    unit_ids: list[uuid.UUID]
    prompt: str
    reference_answer: str
    rubric: str


class HigherQuestionResult(_Strict):
    questions: list[HigherQuestion]
    dropped: list[DroppedQuestion]
