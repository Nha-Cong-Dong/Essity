"""Eval suite for linking a question to cards (US-17, T9.6b): which studied cards does a question
test?

The task does not exist on main yet (T9.6b). The suite runs against a `LinkTask`; until one is
wired, `unwired_link_task` raises in every case, so the report shows errors and no metrics rather
than a made-up pass. Wiring is one line: `make_suite(<the real function>)`.

The label is the set of card ids a person says the question tests. Precision and recall are over
the set; a case is a hit on an exact match. No threshold is set until a first real run (T9.7).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from evals.framework.runner import EvalCase, GuardedAsk, Scored, Suite


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseCard(_Strict):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = ""


class LinkCase(EvalCase):
    question: str = Field(min_length=1)
    cards: list[CaseCard] = Field(min_length=1)
    expected: list[str]  # ids of the cards the question tests

    def check(self) -> None:
        ids = [c.id for c in self.cards]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.id}: duplicate card id")
        if not set(self.expected) <= set(ids):
            raise ValueError(f"{self.id}: expected names a card that is not in cards")


@dataclass(frozen=True)
class LinkRequest:
    question: str
    cards: list[CaseCard]


@dataclass(frozen=True)
class LinkResult:
    card_ids: list[str]


class LinkTask(Protocol):
    def __call__(self, request: LinkRequest, ask: Callable[[Any], str]) -> LinkResult: ...


class TaskNotWiredError(Exception):
    """T9.6b has not landed: there is no link task to measure yet."""


def unwired_link_task(request: LinkRequest, ask: Callable[[Any], str]) -> LinkResult:
    raise TaskNotWiredError


def check_labels(cases: list[LinkCase]) -> None:
    for case in cases:
        case.check()


def make_suite(task: LinkTask) -> Suite[LinkCase]:
    def score(case: LinkCase, ask: GuardedAsk) -> Scored:
        got = set(task(LinkRequest(case.question, case.cards), ask).card_ids)
        want = set(case.expected)
        both = len(got & want)
        return Scored(
            hit=got == want,
            counts={"recall": (both, len(want)), "precision": (both, len(got))},
        )

    return Suite(
        name="link_question",
        case_model=LinkCase,
        task="link_question",
        score=score,
        thresholds={"recall": None, "precision": None},
        check_labels=check_labels,
    )


SUITE = make_suite(unwired_link_task)
