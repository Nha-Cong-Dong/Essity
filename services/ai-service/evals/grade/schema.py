"""The eval dataset for grading (US-05 AC4, AC5, AC7, AC9, AC10): one JSON case per line.

A case holds what a /v1/grade request holds, minus ids (the runner makes them), plus the label
a person gave it. The checks here keep a wrong label from reaching a run: a mislabelled case
measures nothing.
"""

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_service.tasks.grade import derive_overall
from ai_service.tasks.grade_models import Verdict

Category = Literal["general", "paraphrase", "mixed_lang", "typo", "injection"]
# Categories whose answer states the right idea in another form (AC5): always labelled correct.
RIGHT_IDEA: frozenset[str] = frozenset({"paraphrase", "mixed_lang", "typo"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseQuestion(_Strict):
    text: str = Field(min_length=1)
    rubric: str | None = None
    reference_answer: str = Field(min_length=1)


class CaseUnit(_Strict):
    title: str = Field(min_length=1)
    sources: list[str] = Field(min_length=1, max_length=5)


class Expected(_Strict):
    overall: Verdict
    units: list[Verdict] = Field(min_length=1)
    understanding: Literal[1, 2, 3] | None = None


class EvalCase(_Strict):
    id: str = Field(min_length=1)
    category: Category
    # The level of the question (US-04b), for the per-level count (AC10).
    level: Literal[1, 2, 3]
    question: CaseQuestion
    units: list[CaseUnit] = Field(min_length=1, max_length=5)
    answer: str = Field(min_length=1)
    expected: Expected

    @model_validator(mode="after")
    def _label_is_consistent(self) -> Self:
        if not self.answer.strip():
            raise ValueError("answer must not be blank: the service grades it without a model")
        if len(self.expected.units) != len(self.units):
            raise ValueError("expected.units must have one verdict per unit")
        if self.expected.overall != derive_overall(list(self.expected.units)):
            raise ValueError("expected.overall must follow expected.units")
        if self.category in RIGHT_IDEA and self.expected.overall != "correct":
            raise ValueError(f"a {self.category} case states the right idea: expect correct")
        if self.category == "injection" and self.expected.overall == "correct":
            raise ValueError("an injection case cannot expect correct: it would measure nothing")
        return self


def load_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = EvalCase.model_validate(json.loads(line))
        except (ValidationError, json.JSONDecodeError) as error:
            raise ValueError(f"{path.name} line {number}: {_reason(error)}") from None
        if case.id in seen:
            raise ValueError(f"{path.name} line {number}: duplicate id {case.id}")
        seen.add(case.id)
        cases.append(case)
    return cases


def _reason(error: ValidationError | json.JSONDecodeError) -> str:
    # Never echo the input: a case may hold a learner's text.
    if isinstance(error, json.JSONDecodeError):
        return "not valid JSON"
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors())
