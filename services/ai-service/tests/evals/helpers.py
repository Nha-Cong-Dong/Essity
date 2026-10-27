"""Cases and scripted adapters for the eval tests."""

import json
from collections.abc import Callable
from typing import Any

from ai_service.llm.types import AdapterResult, LlmRequest, ProviderError


def case_dict(case_id: str = "c1", **overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "id": case_id,
        "category": "general",
        "level": 1,
        "question": {"text": "TCP opens how?", "reference_answer": "Three-way handshake."},
        "units": [{"title": "Handshake", "sources": ["SYN, SYN-ACK, ACK."]}],
        "answer": "Client sends SYN, server SYN-ACK, client ACK.",
        "expected": {"overall": "correct", "units": ["correct"], "understanding": None},
    }
    case.update(overrides)
    return case


def case_with(case_id: str, overall: str, *, category: str = "general", level: int = 1):
    """A one-unit case labelled `overall`, as a dict."""
    return case_dict(
        case_id,
        category=category,
        level=level,
        expected={"overall": overall, "units": [overall]},
    )


def output(units: list[str], *, understanding: int | None = None) -> str:
    """A model output that passes R03 for a request with `len(units)` units."""
    all_incorrect = all(v == "incorrect" for v in units)
    all_correct = all(v == "correct" for v in units)
    return json.dumps(
        {
            "units": [{"unit": f"U{i}", "verdict": v} for i, v in enumerate(units, start=1)],
            "missing": [] if all_correct else ["something missing"],
            "anchors_used": [] if all_incorrect else ["U1.A1"],
            "understanding": None if all_incorrect else (understanding or 2),
        }
    )


class ScriptedAdapter:
    """Answers each call from `script(call_number, request)`: text or a ProviderError."""

    provider = "fake"
    params: dict[str, Any] = {}

    def __init__(
        self,
        script: Callable[[int, LlmRequest], str | ProviderError],
        *,
        tokens: tuple[int, int] = (0, 0),
        fixed_model: str | None = "fake-grader-v1",
    ) -> None:
        self._script = script
        self._tokens = tokens
        self.fixed_model = fixed_model
        self.calls: list[LlmRequest] = []
        self.models: list[str] = []

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        self.calls.append(request)
        self.models.append(model)
        result = self._script(len(self.calls), request)
        if isinstance(result, ProviderError):
            raise result
        return AdapterResult(
            text=result, input_tokens=self._tokens[0], output_tokens=self._tokens[1]
        )
