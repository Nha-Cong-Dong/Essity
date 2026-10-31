"""Eval suite for `generate_like` (US-17 AC4, AC7): does the generator and its judge keep what a
person would keep, and nothing that leaves the studied cards?

A case holds a request and a label: the status the run should end in, how many questions at
least should survive, and `leak_markers`, words that only an off-source question would contain
(a kept question holding one is a leak: US-17 AC7 allows none). Cards are named C1, C2, ... in
the order given, as in the prompt. No threshold is set until a first real run (T9.7).
"""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_service.tasks.generate_like import (
    LikeRequest,
    SampleQuestion,
    StudiedCard,
    generate_like,
)
from evals.framework.runner import EvalCase, GuardedAsk, Scored, Suite


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Expected(_Strict):
    status: Literal["ok", "empty", "pending_ai"]
    min_kept: int = Field(default=0, ge=0)
    leak_markers: list[str] = []


class LikeCase(EvalCase):
    type_name: str = "Explain"
    samples: list[str] = []
    existing_prompts: list[str] = []
    cards: list[str]  # text of each studied card
    count: int = Field(default=5, ge=1, le=5)
    expected: Expected


def build_request(case: LikeCase) -> LikeRequest:
    return LikeRequest(
        type_name=case.type_name,
        samples=[SampleQuestion(prompt=p) for p in case.samples],
        existing_prompts=case.existing_prompts,
        cards=[
            StudiedCard(
                card_id=uuid.uuid5(uuid.NAMESPACE_URL, f"essity-eval/{case.id}/{n}"), text=t
            )
            for n, t in enumerate(case.cards, start=1)
        ],
        count=case.count,
    )


def score(case: LikeCase, ask: GuardedAsk) -> Scored:
    result = generate_like(build_request(case), ask)
    markers = [m.lower() for m in case.expected.leak_markers]
    leaks = sum(any(m in q.prompt.lower() for m in markers) for q in result.kept)
    hit = (
        result.status == case.expected.status
        and len(result.kept) >= case.expected.min_kept
        and leaks == 0
    )
    return Scored(
        hit=hit,
        counts={
            "status": (int(result.status == case.expected.status), 1),
            "leak_free": (len(result.kept) - leaks, len(result.kept)),
        },
    )


SUITE = Suite(
    name="generate_similar",
    case_model=LikeCase,
    task="generate_like",
    score=score,
    thresholds={"status": None, "leak_free": None},
)
