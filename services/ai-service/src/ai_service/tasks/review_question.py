"""POST /v1/review-question (T7.9, US-02b AC11): one level-1 review question for one saved card.

core-api sends the card (title, summary, anchored quotes) because ai-service holds none of it;
the reply carries the question with its rubric and reference answer, which core stores with the
question so grading never sends the anchors again. One model call per request, through the same
`generate_questions` core as v1 (units: exactly one). Trouble with the model is not an error:
`status: "failed"` (the reply broke a rule) or `status: "pending_ai"` (quota or model down: the
card still enters review, the question comes later). Only an audit failure raises (503).
Results and logs carry rule names only, never the card's text or the model's.
"""

import time
import uuid
from typing import Any, Literal

from ai_service.db.session import SessionFactory
from ai_service.llm.client import LlmClient, LlmUnavailableError
from ai_service.llm.quota import QuotaExceededError, QuotaUnavailableError
from ai_service.llm.types import LlmRequest, LlmResult
from ai_service.tasks import generate_questions as question_task
from ai_service.tasks.generate_questions import (
    QuestionInputError,
    QuestionPrompt,
    QuestionsInvalidError,
)
from ai_service.tasks.practice_run import (
    DEADLINE_SECONDS,
    RunInfo,
    _finish_run,  # pyright: ignore[reportPrivateUsage]
    _start_run,  # pyright: ignore[reportPrivateUsage]
)
from ai_service.tasks.question_models import QuestionRequest, QuestionUnit


class ReviewQuestionBody(QuestionUnit):
    """The card, as `QuestionUnit` limits it (lengths, NUL, at most 5 quotes), plus the owner."""

    user_id: uuid.UUID
    subject_id: uuid.UUID


class ReviewQuestionResponse(RunInfo):
    status: Literal["ok", "failed", "pending_ai"]
    failure: str | None = None
    prompt: str | None = None
    reference_answer: str | None = None
    rubric: str | None = None


def run_review_question(
    body: ReviewQuestionBody, *, llm: LlmClient, sessions: SessionFactory
) -> ReviewQuestionResponse:
    prompt = question_task.load_prompt()
    run_id = _start_run(
        sessions, "generate_questions", body.user_id, body.subject_id, prompt.version, prompt.sha256
    )
    last: list[LlmResult] = []
    deadline = time.monotonic() + DEADLINE_SECONDS

    def ask(built: QuestionPrompt) -> str:
        request = LlmRequest(
            task="generate_questions",
            user_id=body.user_id,
            subject_id=body.subject_id,
            pipeline_run_id=run_id,
            prompt_version=prompt.version,
            attempt=1,
            system=built.system,
            user=built.user,
            output_schema=built.output_schema,
            payload={"labels": ["U1"]},
        )
        last.append(llm.call(request, deadline=deadline))
        return last[-1].text

    unit = QuestionUnit.model_validate(body.model_dump(exclude={"user_id", "subject_id"}))
    status: Literal["ok", "failed", "pending_ai"] = "ok"
    failure: str | None = None
    fields: dict[str, Any] = {}
    try:
        result = question_task.generate_questions(QuestionRequest(units=[unit]), ask)
        question = result.questions[0]
        fields = {
            "prompt": question.prompt,
            "reference_answer": question.reference_answer,
            "rubric": question.rubric,
        }
    except (LlmUnavailableError, QuotaExceededError, QuotaUnavailableError):
        status = "pending_ai"
    except QuestionsInvalidError:
        status, failure = "failed", "output_invalid"
    except QuestionInputError as error:
        status, failure = "failed", error.rule
    code = "quota_or_unavailable" if status == "pending_ai" else failure
    _finish_run(sessions, run_id, code)
    info = last[-1] if last else None
    return ReviewQuestionResponse(
        status=status,
        failure=failure,
        prompt_version=prompt.version,
        run_id=run_id,
        provider=info.provider if info else None,
        model=info.model if info else None,
        llm_call_id=info.llm_call_id if info else None,
        **fields,
    )
