"""Builders for generate_questions tests: a request and a fake `ask` returning canned JSON."""

import json
import uuid
from typing import Any

from ai_service.tasks.generate_questions import QuestionPrompt
from ai_service.tasks.question_models import QuestionRequest, QuestionUnit

U1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
U2 = uuid.UUID("22222222-2222-2222-2222-222222222222")


def request(n: int = 2) -> QuestionRequest:
    ids = [U1, U2] + [uuid.uuid4() for _ in range(max(0, n - 2))]
    return QuestionRequest(
        units=[
            QuestionUnit(
                unit_id=ids[i],
                title=f"Unit {i + 1}",
                summary=f"Summary {i + 1}.",
                quotes=[f"Quote text number {i + 1} from the page."],
            )
            for i in range(n)
        ]
    )


def question_json(label: str = "U1", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "unit": label,
        "prompt": f"Explain {label}?",
        "reference_answer": f"{label} is the thing.",
        "rubric": "Must name the thing. Partial if vague.",
    }
    base.update(kw)
    return base


def output(*questions: dict[str, Any]) -> str:
    return json.dumps({"questions": list(questions)})


def full_output(n: int = 2) -> str:
    return output(*(question_json(f"U{i}") for i in range(1, n + 1)))


class FakeAsk:
    """Returns the canned replies in turn (the last one repeats) and records the prompts."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[QuestionPrompt] = []

    def __call__(self, prompt: QuestionPrompt) -> str:
        self.prompts.append(prompt)
        return self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]
