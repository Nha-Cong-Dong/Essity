"""More practice questions as an HTTP-backed run (T9.6b, US-17).

`generate_like` is a pure core that takes an `ask` function. This module binds it to the
`LlmClient` (quota, audit row, deadline) and records the `pipeline_run` before any paid call.
At most two calls per run (generate, judge) and never a retry (AC6). Trouble with the model never
raises out of the core: it comes back as a status (`empty` with a `failure`, `pending_ai`); only an
audit failure raises (503, fail closed). Results and logs carry rule names only.
"""

import json
import re
import time
import uuid
from contextlib import suppress
from typing import Any

from ai_service.db.session import SessionFactory
from ai_service.llm.client import AuditUnavailableError, LlmClient
from ai_service.llm.types import LlmRequest, LlmResult
from ai_service.tasks import generate_like as like
from ai_service.tasks.generate_like import LikePrompt, LikeRequest, LikeResult
from ai_service.tasks.practice_run import (
    DEADLINE_SECONDS,
    RunInfo,
    _finish_run,  # pyright: ignore[reportPrivateUsage]
    _info,  # pyright: ignore[reportPrivateUsage]
    _start_run,  # pyright: ignore[reportPrivateUsage]
)


class GenerateLikeBody(LikeRequest):
    user_id: uuid.UUID
    subject_id: uuid.UUID


class GenerateLikeResponse(LikeResult, RunInfo):
    pass


class _LikeAsker:
    """`ask` for one run. Keeps the last result for the response."""

    def __init__(
        self,
        llm: LlmClient,
        *,
        user_id: uuid.UUID,
        subject_id: uuid.UUID,
        run_id: uuid.UUID,
        count: int,
        cards: int,
        deadline: float,
    ) -> None:
        self.llm, self.deadline = llm, deadline
        self.user_id, self.subject_id, self.run_id = user_id, subject_id, run_id
        self.count, self.cards = count, cards
        self.last: LlmResult | None = None

    def __call__(self, prompt: LikePrompt) -> str:
        # `payload` is for the fake provider only, never sent to a real one.
        payload: dict[str, Any] = {"count": self.count, "cards": self.cards}
        request = LlmRequest(
            task=prompt.task,
            user_id=self.user_id,
            subject_id=self.subject_id,
            pipeline_run_id=self.run_id,
            prompt_version=like.PROMPT_VERSION,
            attempt=1,
            system=prompt.system,
            user=prompt.user,
            output_schema=prompt.output_schema,
            payload=payload,
        )
        self.last = self.llm.call(request, deadline=self.deadline)
        return self.last.text


def _code(result: LikeResult) -> str | None:
    if result.status == "pending_ai":
        return "quota_or_unavailable"
    return result.failure


def run_generate_like(
    body: GenerateLikeBody, *, llm: LlmClient, sessions: SessionFactory
) -> GenerateLikeResponse:
    request = LikeRequest.model_validate(body.model_dump(exclude={"user_id", "subject_id"}))
    prompt = like.load_prompt(like.GENERATE_TASK)
    run_id = _start_run(
        sessions, "generate_like", body.user_id, body.subject_id, prompt.version, prompt.sha256
    )
    asker = _LikeAsker(
        llm,
        user_id=body.user_id,
        subject_id=body.subject_id,
        run_id=run_id,
        count=request.count,
        cards=len(request.cards),
        deadline=time.monotonic() + DEADLINE_SECONDS,
    )
    try:
        result = like.generate_like(request, asker)
    except AuditUnavailableError:
        raise
    except Exception:
        with suppress(AuditUnavailableError):
            _finish_run(sessions, run_id, "internal_error")
        raise
    _finish_run(sessions, run_id, _code(result))
    return GenerateLikeResponse(
        **result.model_dump(),
        prompt_version=prompt.version,
        run_id=run_id,
        **_info(asker),  # pyright: ignore[reportArgumentType]
    )


# --- Fakes (AI_LLM_PROVIDER=fake: local and test only) -----------------------------------------


def fake_generate_like(request: LlmRequest) -> str:
    """`count` candidates, each citing the first card and different enough from each other."""
    topics = ["causes", "effects", "an example of", "limits of", "a comparison involving"]
    count = int(request.payload.get("count", 1))
    candidates = [
        {
            "prompt": f"Discuss {topics[n % len(topics)]} the idea in card one, variant {n + 1}",
            "reference_answer": "Answer drawn from the card.",
            "rubric": "Names the idea. Uses the card.",
            "cards": ["C1"],
        }
        for n in range(count)
    ]
    return json.dumps({"candidates": candidates})


def fake_judge_questions(request: LlmRequest) -> str:
    """Every candidate passes. The labels are read from the prompt the code built."""
    labels = re.findall(r'kind="candidate" label="(Q\d+)"', request.user)
    verdicts = [
        {"candidate": label, "j1": True, "j2": True, "j3": True, "j4": True, "j5": True}
        for label in labels
    ]
    return json.dumps({"verdicts": verdicts})
