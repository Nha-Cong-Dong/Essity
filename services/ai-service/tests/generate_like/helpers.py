"""Builders for generate_like tests: a request and a fake `ask` returning canned JSON."""

import json
import uuid
from typing import Any

from ai_service.tasks.generate_like import (
    LikePrompt,
    LikeRequest,
    SampleQuestion,
    StudiedCard,
)

C1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
C2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
SAMPLE = "Explain how the cell membrane controls what enters the cell."


def request(**kw: Any) -> LikeRequest:
    base: dict[str, Any] = {
        "type_name": "Explain",
        "samples": [SampleQuestion(prompt=SAMPLE)],
        "cards": [
            StudiedCard(card_id=C1, text="Osmosis moves water across a membrane."),
            StudiedCard(card_id=C2, text="Mitochondria produce ATP."),
        ],
    }
    base.update(kw)
    return LikeRequest(**base)


def cand(n: int = 1, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "prompt": f"Describe in detail the role number {n} that mitochondria play for the cell",
        "reference_answer": "They make ATP.",
        "rubric": "Names ATP. Partial if vague.",
        "cards": ["C2"],
    }
    base.update(kw)
    return base


def gen(*cands: dict[str, Any]) -> str:
    return json.dumps({"candidates": list(cands)})


def verdict(label: str, **kw: bool) -> dict[str, Any]:
    base: dict[str, Any] = {
        "candidate": label,
        "j1": True,
        "j2": True,
        "j3": True,
        "j4": True,
        "j5": True,
    }
    base.update(kw)
    return base


def judged(*verdicts: dict[str, Any]) -> str:
    return json.dumps({"verdicts": list(verdicts)})


class FakeAsk:
    """Returns the canned replies in turn (the last one repeats) and records the prompts. An
    Exception in the list is raised instead."""

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.prompts: list[LikePrompt] = []

    def __call__(self, prompt: LikePrompt) -> str:
        self.prompts.append(prompt)
        reply = self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply
