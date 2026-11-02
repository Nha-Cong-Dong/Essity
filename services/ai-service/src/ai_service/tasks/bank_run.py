"""A question bank as an HTTP-backed run (T8.1b, US-14).

The cores of `question_bank` (`split_bank`, `suggest_types`, `map_sections`) take an `ask`
function. This module binds it to the `LlmClient` (quota, audit row, deadline) under the task
`parse_question_bank`, one `pipeline_run` for the three steps, recorded before any paid call.
Numbered banks cost no split call; questions go to the model in batches of `CHUNK_QUESTIONS`.

Trouble with the model never raises out of a core: it comes back as a status. `pending_ai` (the
quota stopped a step) returns nothing to store, so the caller never keeps a half-typed bank that
a repeated import could not complete (the content hash would skip it). Only an audit failure
raises (503, fail closed). Results and logs carry rule names only, never a question or answer.
"""

import hashlib
import json
import re
import time
import uuid
from contextlib import suppress
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_service.db.session import SessionFactory
from ai_service.llm.client import AuditUnavailableError, LlmClient
from ai_service.llm.types import LlmRequest, LlmResult
from ai_service.pdf import PageText
from ai_service.tasks import question_bank as bank
from ai_service.tasks.practice_run import (
    RunInfo,
    _finish_run,  # pyright: ignore[reportPrivateUsage]
    _info,  # pyright: ignore[reportPrivateUsage]
    _start_run,  # pyright: ignore[reportPrivateUsage]
)

DEADLINE_SECONDS = 120.0  # a few dozen batched calls, not one
MAX_PAGES = 400
_STEPS = {"LlmSplit": "split", "LlmTypes": "types", "LlmMappings": "sections"}
_PROMPT_NAMES = ("bank_split", "bank_types", "bank_sections")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PageIn(_Strict):
    text: Annotated[str, Field(max_length=200_000)]
    needs_vision: bool = False


class SectionIn(_Strict):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    title: Annotated[str, Field(max_length=300)]


class ParseBankBody(_Strict):
    user_id: uuid.UUID
    subject_id: uuid.UUID
    pages: Annotated[list[PageIn], Field(max_length=MAX_PAGES)]
    existing_types: Annotated[
        list[Annotated[str, Field(max_length=200)]], Field(max_length=100)
    ] = []
    sections: Annotated[list[SectionIn], Field(max_length=bank.MAX_SECTIONS)] = []


class QuestionOut(_Strict):
    ord: int
    prompt: str
    # The bank's own words, never written by the model (AC1); None when the bank gives none.
    answer_text: str | None
    source_page: int
    type_name: str | None
    section_ids: list[str]


class ParseBankResult(_Strict):
    status: Literal["ok", "partial", "pending_ai"]
    questions: list[QuestionOut]
    unmapped: list[int]
    reasons: list[str]  # rule names only


class ParseBankResponse(ParseBankResult, RunInfo):
    pass


def prompt_sha256() -> str:
    joined = "".join(bank.load_prompt(name).sha256 for name in _PROMPT_NAMES)
    return hashlib.sha256(joined.encode()).hexdigest()


class _BankAsker:
    """`ask` for one run: builds the `LlmRequest`, keeps the last result for the response."""

    def __init__(
        self,
        llm: LlmClient,
        *,
        user_id: uuid.UUID,
        subject_id: uuid.UUID,
        run_id: uuid.UUID,
        deadline: float,
    ) -> None:
        self.llm, self.deadline = llm, deadline
        self.user_id, self.subject_id, self.run_id = user_id, subject_id, run_id
        self.last: LlmResult | None = None

    def __call__(self, prompt: bank.BankPrompt) -> str:
        step = _STEPS.get(str(prompt.output_schema.get("title")), "split")
        request = LlmRequest(
            task="parse_question_bank",
            user_id=self.user_id,
            subject_id=self.subject_id,
            pipeline_run_id=self.run_id,
            prompt_version=bank.PROMPT_VERSION,
            attempt=1,
            system=prompt.system,
            user=prompt.user,
            output_schema=prompt.output_schema,
            payload={"step": step},  # for the fake provider only, never sent to a real one
        )
        self.last = self.llm.call(request, deadline=self.deadline)
        return self.last.text


def parse_bank(body: ParseBankBody, ask: bank.Ask) -> ParseBankResult:
    pages = [PageText(text=p.text, needs_vision=p.needs_vision) for p in body.pages]
    split = bank.split_bank(pages, ask)
    types = bank.suggest_types(split.questions, body.existing_types, ask)
    sections = bank.map_sections(
        split.questions, [bank.Section(s.id, s.title) for s in body.sections], ask
    )
    results = (split, types, sections)
    reasons = list(dict.fromkeys(r.code for result in results for r in result.reasons))
    if any(r.status == "pending_ai" for r in results):
        return ParseBankResult(status="pending_ai", questions=[], unmapped=[], reasons=reasons)
    status: Literal["ok", "partial"] = (
        "partial" if any(r.status == "partial" for r in results) else "ok"
    )
    questions = [
        QuestionOut(
            ord=q.ord,
            prompt=q.prompt,
            answer_text=q.answer_text,
            source_page=q.source_page,
            type_name=types.assignment.get(q.ord),
            section_ids=sections.mapping.get(q.ord, []),
        )
        for q in split.questions
    ]
    return ParseBankResult(
        status=status, questions=questions, unmapped=sections.unmapped, reasons=reasons
    )


def run_parse_question_bank(
    body: ParseBankBody, *, llm: LlmClient, sessions: SessionFactory
) -> ParseBankResponse:
    run_id = _start_run(
        sessions,
        "parse_question_bank",
        body.user_id,
        body.subject_id,
        bank.PROMPT_VERSION,
        prompt_sha256(),
    )
    asker = _BankAsker(
        llm,
        user_id=body.user_id,
        subject_id=body.subject_id,
        run_id=run_id,
        deadline=time.monotonic() + DEADLINE_SECONDS,
    )
    try:
        result = parse_bank(body, asker)
    except AuditUnavailableError:
        raise
    except Exception:
        with suppress(AuditUnavailableError):
            _finish_run(sessions, run_id, "internal_error")
        raise
    code = "quota_or_unavailable" if result.status == "pending_ai" else None
    _finish_run(sessions, run_id, code)
    return ParseBankResponse(
        **result.model_dump(),
        prompt_version=bank.PROMPT_VERSION,
        run_id=run_id,
        **_info(asker),  # pyright: ignore[reportArgumentType]
    )


# --- Fake (AI_LLM_PROVIDER=fake: local and test only) ------------------------------------------


def fake_parse_question_bank(request: LlmRequest) -> str:
    """Numbered banks need no split call, so the fake answers an empty split, one type for every
    question and the first section for every question."""
    step = request.payload.get("step")
    questions = re.findall(r'kind="question" label="(Q\d+)"', request.user)
    if step == "types":
        types: list[dict[str, Any]] = (
            [{"name": "Giải thích", "questions": questions}] if questions else []
        )
        return json.dumps({"types": types}, ensure_ascii=False)
    if step == "sections":
        has_section = 'kind="section" label="S1"' in request.user
        mappings = [{"question": q, "sections": ["S1"]} for q in questions] if has_section else []
        return json.dumps({"mappings": mappings})
    return json.dumps({"questions": []})
