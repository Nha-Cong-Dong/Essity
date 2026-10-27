"""ai-service's /v1/grade as the routes see it in tests (T2.13): every unit correct, or the
failure a test sets; every payload kept."""

import uuid
from collections.abc import Mapping
from typing import Any

from core_api.clients.ai_client import Graded, NotGraded
from core_api.clients.grade_contract import GradeResponse


class Stub:
    def __init__(self) -> None:
        self.failure: NotGraded | None = None
        self.provider = "anthropic"
        self.calls: list[Mapping[str, object]] = []

    def grade(self, payload: Mapping[str, object]) -> Graded | NotGraded:
        self.calls.append(payload)
        if self.failure is not None:
            return self.failure
        units: Any = payload["units"]
        return Graded(
            GradeResponse.model_validate(
                {
                    "provider": self.provider,
                    "model": "m",
                    "prompt_version": "v1",
                    "run_id": str(uuid.uuid4()),
                    "llm_call_id": str(uuid.uuid4()),
                    "overall": "correct",
                    "understanding": 3,
                    "missing": [],
                    "units": [{"unit_id": u["unit_id"], "verdict": "correct"} for u in units],
                    "anchors_used": [units[0]["anchors"][0]["anchor_id"]],
                }
            )
        )
