"""The /v1/grade contract (T2.12). core-api is the only caller.

Limits (G6, review of the plan 25/10): answer up to 4000 characters, up to 5 units, up to 5
anchors per unit, up to 12000 characters of source text in all, question, rubric and reference
answer up to 4000 characters each, unit title up to 200 (as `knowledge_unit.title` in core).
"""

import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

MAX_ANSWER_CHARS = 4000
MAX_UNITS = 5
MAX_ANCHORS_PER_UNIT = 5
MAX_QUOTE_CHARS = 12000
MAX_QUESTION_CHARS = 4000
MAX_TITLE_CHARS = 200
MAX_MISSING_ITEMS = 3
MAX_MISSING_CHARS = 200

Verdict = Literal["correct", "partial", "incorrect"]
# Who graded: a model's provider, the fake grader, or nobody (empty answer). core decides
# on this value (R41), so nothing else may leave the service.
Provider = Literal["anthropic", "fake", "none"]


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("must not be blank")
    return text


QuestionText = Annotated[
    str, Field(min_length=1, max_length=MAX_QUESTION_CHARS), AfterValidator(_not_blank)
]
Title = Annotated[str, Field(min_length=1, max_length=MAX_TITLE_CHARS), AfterValidator(_not_blank)]
Quote = Annotated[str, Field(min_length=1, max_length=MAX_QUOTE_CHARS), AfterValidator(_not_blank)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GradeQuestion(_Strict):
    text: QuestionText
    rubric: Annotated[str, Field(max_length=MAX_QUESTION_CHARS)] | None = None
    reference_answer: QuestionText


class GradeAnchor(_Strict):
    anchor_id: uuid.UUID
    quote_text: Quote


class GradeUnit(_Strict):
    unit_id: uuid.UUID
    title: Title
    anchors: list[GradeAnchor] = Field(min_length=1, max_length=MAX_ANCHORS_PER_UNIT)


class GradeRequest(_Strict):
    user_id: uuid.UUID
    subject_id: uuid.UUID
    attempt_id: uuid.UUID | None = None
    question: GradeQuestion
    # May be empty: an empty answer is graded incorrect without calling a model (🟠6).
    answer: str = Field(max_length=MAX_ANSWER_CHARS)
    units: list[GradeUnit] = Field(min_length=1, max_length=MAX_UNITS)

    @model_validator(mode="after")
    def _ids_unique_and_sources_bounded(self) -> "GradeRequest":
        unit_ids = [unit.unit_id for unit in self.units]
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("unit_id must be unique")
        anchors = [anchor for unit in self.units for anchor in unit.anchors]
        if len({anchor.anchor_id for anchor in anchors}) != len(anchors):
            raise ValueError("anchor_id must be unique across units")
        if sum(len(anchor.quote_text) for anchor in anchors) > MAX_QUOTE_CHARS:
            raise ValueError(f"quote_text must total at most {MAX_QUOTE_CHARS} characters")
        return self


class UnitVerdict(_Strict):
    unit_id: uuid.UUID
    verdict: Verdict


class GradeResponse(_Strict):
    # "fake" from the fake grader; "none" when no model was asked (empty answer).
    provider: Provider
    model: str | None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None
    overall: Verdict
    # 1 recall, 2 understands why, 3 can apply (US-05). None when overall is incorrect.
    understanding: Literal[1, 2, 3] | None
    missing: list[str]
    units: list[UnitVerdict]
    anchors_used: list[uuid.UUID]
