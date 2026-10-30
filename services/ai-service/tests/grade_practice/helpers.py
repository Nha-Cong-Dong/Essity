"""Builders for grade_practice and draft_answer tests: a request and a fake `ask`."""

import json
from typing import Any

from ai_service.tasks.grade_practice import PracticeGradeRequest

ANSWER = "Client gui SYN, server tra SYN-ACK, roi client gui ACK."


def request(**kw: Any) -> PracticeGradeRequest:
    base: dict[str, Any] = {
        "question": "TCP opens a connection how?",
        "rubric": ["Three steps", "Names SYN, SYN-ACK, ACK"],
        "reference_answer": "Three-way handshake: SYN, SYN-ACK, ACK.",
        "answer": ANSWER,
    }
    base.update(kw)
    return PracticeGradeRequest(**base)


def idea(label: str, verdict: str, anchor: str | None = None) -> dict[str, Any]:
    return {"idea": label, "verdict": verdict, "anchor": anchor}


def reply(*ideas: dict[str, Any]) -> str:
    return json.dumps({"ideas": list(ideas)})


class FakeAsk:
    """Returns the canned replies in turn (the last one repeats) and records the prompts. An
    Exception in the list is raised instead."""

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.prompts: list[Any] = []

    def __call__(self, prompt: Any) -> str:
        self.prompts.append(prompt)
        item = self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]
        if isinstance(item, Exception):
            raise item
        return item
