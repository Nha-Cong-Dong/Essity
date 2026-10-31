"""Eval suite for `draft_units` (US-02b AC2): does the split into draft units match what a learner
would keep?

The label is a list of units the learner kept after review (later: their own corrections, rev 1),
each named by one quote that its draft must anchor. A draft matches a unit when one of its
anchors' quotes contains that quote; one draft serves one unit. Recall is matched / labelled
units, precision is matched / drafts (a split idea or an extra draft lowers it). The "one idea"
rubric (Q18) is not written yet, so no threshold is set.
"""

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_service.tasks.draft_units import (
    Draft,
    DraftRequest,
    ScopedDoc,
    ScopedPage,
    draft_units,
)
from evals.framework.runner import EvalCase, GuardedAsk, Scored, Suite


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseDoc(_Strict):
    name: str = Field(min_length=1)
    pages: list[str] = Field(min_length=1)  # page text, numbered from 1


class ExpectedUnit(_Strict):
    quote: str = Field(min_length=1)


class DraftCase(EvalCase):
    docs: list[CaseDoc] = []
    notes: str | None = None
    description: str | None = None
    expected: list[ExpectedUnit]

    @model_validator(mode="after")
    def _has_input(self) -> Self:
        if not self.docs and not (self.notes and self.notes.strip()):
            raise ValueError("a case needs documents or notes")
        return self


def _id(case: DraftCase, *parts: object) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "/".join(["essity-eval", case.id, *map(str, parts)]))


def build_request(case: DraftCase) -> DraftRequest:
    return DraftRequest(
        session_id=_id(case, "session"),
        scope=[
            ScopedDoc(
                document_id=_id(case, "doc", d),
                name=doc.name,
                pages=[ScopedPage(page_no=n, text=t) for n, t in enumerate(doc.pages, start=1)],
            )
            for d, doc in enumerate(case.docs)
        ],
        submission_text=case.notes,
        description=case.description,
    )


def _fold(text: str) -> str:
    return " ".join(text.lower().split())


def match_count(expected: list[ExpectedUnit], drafts: list[Draft]) -> int:
    free = list(drafts)
    matched = 0
    for unit in expected:
        want = _fold(unit.quote)
        for draft in free:
            if any(want in _fold(a.quote) for a in draft.anchors):
                free.remove(draft)
                matched += 1
                break
    return matched


def score(case: DraftCase, ask: GuardedAsk) -> Scored:
    outcome = draft_units(build_request(case), ask)
    matched = match_count(case.expected, outcome.drafts)
    counts = {
        "recall": (matched, len(case.expected)),
        "precision": (matched, len(outcome.drafts)),
    }
    hit = matched == len(case.expected) == len(outcome.drafts)
    return Scored(hit=hit, counts=counts)


SUITE = Suite(
    name="draft_units",
    case_model=DraftCase,
    task="draft_units",
    score=score,
    # Unset until the first real data (PLAN T9.7): the rubric for "one idea" (Q18) is still open.
    thresholds={"recall": None, "precision": None},
)
