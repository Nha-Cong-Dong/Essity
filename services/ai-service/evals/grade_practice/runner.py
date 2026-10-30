"""Eval scaffold for practice grading (T8.4a, PLAN T8.4: >= 40 labelled pairs, per-idea match
>= 85%, "graded Correct but really Incorrect" <= 5%).

    from evals.grade_practice.runner import load_cases, run
    report = run(load_cases(path), ask)

`ask` is the same callable `grade_practice` takes. Nothing here calls a real model: the T8.4 binding
(and the API key) supplies the real `ask`; the sample file holds a few pairs only, the full set
of 40 is written with that run. The report holds numbers and case ids, never an answer.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_service.tasks.grade import derive_overall
from ai_service.tasks.grade_models import Verdict
from ai_service.tasks.grade_practice import (
    PracticeGradeRequest,
    PracticePrompt,
    grade_practice,
)

MIN_MATCH = 0.85
MAX_FALSE_CORRECT = 0.05
_TO_VERDICT: dict[str, Verdict] = {"yes": "correct", "partial": "partial", "no": "incorrect"}


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    category: Literal["bank_answer", "ai_answer", "injection"]
    question: str
    rubric: list[str] = Field(min_length=1)
    reference_answer: str
    answer: str
    expected: list[Literal["yes", "partial", "no"]] = Field(min_length=1)


@dataclass
class Report:
    ideas: int = 0
    matched: int = 0
    cases: int = 0
    false_correct: int = 0
    not_graded: list[str] = field(default_factory=list[str])

    @property
    def match_rate(self) -> float:
        return self.matched / self.ideas if self.ideas else 0.0

    @property
    def false_correct_rate(self) -> float:
        return self.false_correct / self.cases if self.cases else 0.0

    @property
    def passed(self) -> bool:
        return (
            self.cases > 0
            and not self.not_graded
            and self.match_rate >= MIN_MATCH
            and self.false_correct_rate <= MAX_FALSE_CORRECT
        )


def load_cases(path: Path) -> list[EvalCase]:
    cases = [
        EvalCase.model_validate_json(line)
        for line in path.read_text("utf-8").splitlines()
        if line.strip()
    ]
    for case in cases:
        if len(case.expected) != len(case.rubric):
            raise ValueError(f"{case.id}: expected and rubric differ in length")
    if len({c.id for c in cases}) != len(cases):
        raise ValueError("duplicate case id")
    return cases


def run(cases: list[EvalCase], ask: Callable[[PracticePrompt], str]) -> Report:
    """A case the model did not grade (failed or pending) stays in every denominator as a miss."""
    report = Report()
    for case in cases:
        report.cases += 1
        report.ideas += len(case.expected)
        result = grade_practice(
            PracticeGradeRequest(
                question=case.question,
                rubric=case.rubric,
                reference_answer=case.reference_answer,
                answer=case.answer,
            ),
            ask,
        )
        if result.status != "ok":
            report.not_graded.append(case.id)
            continue
        report.matched += sum(
            got.verdict == _TO_VERDICT[want]
            for got, want in zip(result.ideas, case.expected, strict=True)
        )
        expected_overall = derive_overall([_TO_VERDICT[w] for w in case.expected])
        if result.overall == "correct" and expected_overall == "incorrect":
            report.false_correct += 1
    return report
