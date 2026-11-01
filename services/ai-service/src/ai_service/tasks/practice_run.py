"""Practice grading and answer drafting as HTTP-backed runs (T8.4, US-05 AC9-AC14).

The pure cores (`grade_practice`, `draft_answer`) take an `ask` function. This module binds it to
the `LlmClient` (quota, audit row, deadline) and records the `pipeline_run` before any paid call
(no call without its run). Trouble with the model never raises out of a core: it comes back as a
result status (`failed`, `pending_ai`). Only an audit failure raises (503, fail closed).
Results and logs carry rule names only, never the learner's answer or the model's text.
"""

import json
import logging
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, update

from ai_service.db.models import PipelineRun
from ai_service.db.session import SessionFactory
from ai_service.llm.client import AuditUnavailableError, LlmClient
from ai_service.llm.types import LlmRequest, LlmResult
from ai_service.tasks import draft_answer as draft_task
from ai_service.tasks import grade_practice as grade_task
from ai_service.tasks.draft_answer import DraftPrompt, DraftRequest, DraftResult
from ai_service.tasks.grade_practice import (
    PracticeGradeRequest,
    PracticeGradeResult,
    PracticePrompt,
)

_log = logging.getLogger(__name__)

DEADLINE_SECONDS = 20.0
Task = Literal["grade_practice", "draft_answer"]


class GradePracticeBody(PracticeGradeRequest):
    user_id: uuid.UUID
    subject_id: uuid.UUID


class DraftAnswerBody(DraftRequest):
    user_id: uuid.UUID
    subject_id: uuid.UUID


class RunInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str | None = None
    model: str | None = None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None = None


class GradePracticeResponse(PracticeGradeResult, RunInfo):
    pass


class DraftAnswerResponse(DraftResult, RunInfo):
    pass


def _start_run(
    sessions: SessionFactory,
    task: Task,
    user_id: uuid.UUID,
    subject_id: uuid.UUID,
    version: str,
    sha256: str,
) -> uuid.UUID:
    run = PipelineRun(
        user_id=user_id,
        subject_id=subject_id,
        task=task,
        prompt_version=version,
        prompt_sha256=sha256,
    )
    try:
        with sessions() as session:
            session.add(run)
            session.commit()
    except Exception as error:
        _log.exception("pipeline_run not written")
        raise AuditUnavailableError from error
    return run.id


def _finish_run(sessions: SessionFactory, run_id: uuid.UUID, error_code: str | None) -> None:
    try:
        with sessions() as session:
            session.execute(
                update(PipelineRun)
                .where(PipelineRun.id == run_id)
                .values(
                    status="failed" if error_code else "succeeded",
                    error_code=error_code,
                    finished_at=func.now(),
                )
            )
            session.commit()
    except Exception as error:
        _log.exception("pipeline_run not closed")
        raise AuditUnavailableError from error


class _Asker:
    """`ask` for one run: builds the `LlmRequest`, keeps the last result for the response."""

    def __init__(
        self,
        llm: LlmClient,
        *,
        user_id: uuid.UUID,
        subject_id: uuid.UUID,
        run_id: uuid.UUID,
        version: str,
        payload: dict[str, Any],
        deadline: float,
    ) -> None:
        self.llm, self.deadline = llm, deadline
        self.user_id, self.subject_id, self.run_id = user_id, subject_id, run_id
        self.version, self.payload = version, payload
        self.last: LlmResult | None = None

    def __call__(self, prompt: PracticePrompt | DraftPrompt) -> str:
        request = LlmRequest(
            task=prompt.task,
            user_id=self.user_id,
            subject_id=self.subject_id,
            pipeline_run_id=self.run_id,
            prompt_version=self.version,
            attempt=1,
            system=prompt.system,
            user=prompt.user,
            output_schema=prompt.output_schema,
            payload=self.payload,
        )
        self.last = self.llm.call(request, deadline=self.deadline)
        return self.last.text


def _run[R](
    task: Task,
    body: GradePracticeBody | DraftAnswerBody,
    *,
    llm: LlmClient,
    sessions: SessionFactory,
    version: str,
    sha256: str,
    payload: dict[str, Any],
    core: Callable[[Callable[[Any], str]], R],
    code_of: Callable[[R], str | None],
) -> tuple[R, uuid.UUID, _Asker]:
    run_id = _start_run(sessions, task, body.user_id, body.subject_id, version, sha256)
    asker = _Asker(
        llm,
        user_id=body.user_id,
        subject_id=body.subject_id,
        run_id=run_id,
        version=version,
        payload=payload,
        deadline=time.monotonic() + DEADLINE_SECONDS,
    )
    try:
        result = core(asker)
    except AuditUnavailableError:
        raise
    except Exception:
        with suppress(AuditUnavailableError):
            _finish_run(sessions, run_id, "internal_error")
        raise
    _finish_run(sessions, run_id, code_of(result))
    return result, run_id, asker


def _info(asker: _Asker) -> dict[str, Any]:
    last = asker.last
    return {
        "provider": last.provider if last else None,
        "model": last.model if last else None,
        "llm_call_id": last.llm_call_id if last else None,
    }


def _grade_code(result: PracticeGradeResult) -> str | None:
    if result.status == "pending_ai":
        return "quota_or_unavailable"
    return result.failure


def _draft_code(result: DraftResult) -> str | None:
    if result.status == "pending_ai":
        return "quota_or_unavailable"
    return result.failure


def run_grade_practice(
    body: GradePracticeBody, *, llm: LlmClient, sessions: SessionFactory
) -> GradePracticeResponse:
    request = PracticeGradeRequest.model_validate(
        body.model_dump(exclude={"user_id", "subject_id"})
    )
    prompt = grade_task.load_prompt()
    payload: dict[str, Any] = {
        "answer": request.answer,
        "reference": request.reference_answer,
        "ideas": len(request.rubric),
    }
    result, run_id, asker = _run(
        "grade_practice",
        body,
        llm=llm,
        sessions=sessions,
        version=prompt.version,
        sha256=prompt.sha256,
        payload=payload,
        core=lambda ask: grade_task.grade_practice(request, ask),
        code_of=_grade_code,
    )
    return GradePracticeResponse(
        **result.model_dump(), prompt_version=prompt.version, run_id=run_id, **_info(asker)
    )


def run_draft_answer(
    body: DraftAnswerBody, *, llm: LlmClient, sessions: SessionFactory
) -> DraftAnswerResponse:
    request = DraftRequest.model_validate(body.model_dump(exclude={"user_id", "subject_id"}))
    payload: dict[str, Any] = {
        "question": request.question,
        "cards": [str(c.card_id) for c in request.cards],
    }
    result, run_id, asker = _run(
        "draft_answer",
        body,
        llm=llm,
        sessions=sessions,
        version=draft_task.PROMPT_VERSION,
        sha256=draft_task.prompt_sha256(),
        payload=payload,
        core=lambda ask: draft_task.draft_answer(request, ask),
        code_of=_draft_code,
    )
    return DraftAnswerResponse(
        **result.model_dump(),
        prompt_version=draft_task.PROMPT_VERSION,
        run_id=run_id,
        **_info(asker),
    )


# --- Fakes (AI_LLM_PROVIDER=fake: local and test only) -----------------------------------------


def fake_grade_practice(request: LlmRequest) -> str:
    """Every idea `yes` when the answer shares a word with the reference, else `no`."""
    payload = request.payload
    words = {w for w in str(payload["reference"]).casefold().split() if len(w) > 3}
    got = any(w in str(payload["answer"]).casefold() for w in words)
    verdict = "yes" if got else "no"
    ideas = [
        {"idea": f"R{n}", "verdict": verdict, "anchor": None}
        for n in range(1, int(payload["ideas"]) + 1)
    ]
    return json.dumps({"ideas": ideas})


def fake_draft_answer(request: LlmRequest) -> str:
    return json.dumps({"answer": "Đáp án nháp do AI soạn.", "cards": []}, ensure_ascii=False)
