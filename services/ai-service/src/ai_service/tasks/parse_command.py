"""Turning one command line into one fixed operation (T9.1, US-18, ADR-0030).

How a request becomes a prompt (same rules as grade, ADR-0010):

- The instructions are `prompts/parse_command/v<N>.md`, the system prompt. Only the nonce is
  filled in.
- The command and every title are untrusted text. They go into the user message through
  `wrap_untrusted` (escaped, in a block tagged with a nonce drawn for the request). The model sees
  labels (`C1`, `S3`, ...), never ids, and no document text exists in the request (AC7).
- The output is checked by code: a member of the fixed union (`commands.schema.Command`) with
  labels the request defined, nothing else. A broken output is asked for once more; twice is
  `parse_command_invalid`. Not understanding is an answer (`unclear`), not an error.
"""

import datetime
import hashlib
import json
import logging
import re
import time
import unicodedata
import uuid
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, update

from ai_service.commands.schema import (
    OPERATIONS,
    REFS,
    Command,
    ContextItem,
    LabelKind,
    ParseCommandRequest,
    ParseCommandResponse,
    check_dates,
)
from ai_service.db.models import PipelineRun
from ai_service.db.session import SessionFactory
from ai_service.llm.client import AuditUnavailableError, LlmClient, LlmUnavailableError
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import LlmRequest
from ai_service.tasks.grade import Prompt, new_nonce, wrap_untrusted

_log = logging.getLogger(__name__)

TASK = "parse_command"
PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"

# One short call per command; core cuts at 8 s (the command bar is synchronous, ADR-0030).
DEADLINE_SECONDS = 6.0
RETRY_MIN_SECONDS = 1.5

# Label letter per list of the context.
_PREFIX: dict[LabelKind, str] = {
    "card": "C",
    "section": "S",
    "subject": "J",
    "question_type": "T",
    "question": "Q",
    "document": "D",
}
_SIMPLE_KEYS = {"type", "enum", "const", "items", "anyOf", "properties", "required"}
_ADAPTER: TypeAdapter[Command] = TypeAdapter(Command)


def _simplify(schema: Any) -> Any:
    """The parts of a pydantic schema a provider's structured output takes (no bounds, formats)."""
    if isinstance(schema, list):
        return [_simplify(item) for item in cast(list[Any], schema)]
    if not isinstance(schema, dict):
        return schema
    node = cast(dict[str, Any], schema)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties":
            out[key] = {name: _simplify(prop) for name, prop in cast(dict[str, Any], value).items()}
        elif key in _SIMPLE_KEYS:
            out[key] = _simplify(value)
    if out.get("type") == "object":
        out["additionalProperties"] = False
    return out


def _output_schema() -> dict[str, Any]:
    variants = [_simplify(model.model_json_schema()) for model in OPERATIONS.values()]
    return {
        "type": "object",
        "properties": {"result": {"anyOf": variants}},
        "required": ["result"],
        "additionalProperties": False,
    }


OUTPUT_SCHEMA: dict[str, Any] = _output_schema()


@lru_cache
def load_prompt(version: str = PROMPT_VERSION) -> Prompt:
    path = _PROMPTS / TASK / f"{version}.md"
    text = path.read_text("utf-8")
    return Prompt(
        version=version,
        text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        path=str(path),
    )


# --- The context as the model sees it --------------------------------------------------------


@dataclass(frozen=True)
class Labels:
    """Label -> id for each list of the context."""

    ids: dict[LabelKind, dict[str, uuid.UUID]]
    titles: dict[LabelKind, dict[str, str]]

    @classmethod
    def of(cls, request: ParseCommandRequest) -> "Labels":
        lists: dict[LabelKind, list[ContextItem]] = {
            "card": list(request.cards),
            "section": list(request.sections),
            "subject": list(request.subjects),
            "question_type": list(request.question_types),
            "question": list(request.questions),
            "document": list(request.documents),
        }
        ids: dict[LabelKind, dict[str, uuid.UUID]] = {}
        titles: dict[LabelKind, dict[str, str]] = {}
        for kind, items in lists.items():
            labelled = {f"{_PREFIX[kind]}{n}": item for n, item in enumerate(items, start=1)}
            ids[kind] = {label: item.id for label, item in labelled.items()}
            titles[kind] = {label: item.title for label, item in labelled.items()}
        return cls(ids=ids, titles=titles)


def build_llm_request(
    request: ParseCommandRequest,
    labels: Labels,
    *,
    run_id: uuid.UUID,
    attempt: int,
    nonce: str | None = None,
) -> LlmRequest:
    nonce = nonce or new_nonce()
    prompt = load_prompt()
    parts = [
        wrap_untrusted("command", request.command, nonce),
        wrap_untrusted("today", request.today.isoformat(), nonce),
    ]
    for kind, titles in labels.titles.items():
        parts.extend(
            wrap_untrusted(kind, title, nonce, label=label) for label, title in titles.items()
        )
    return LlmRequest(
        task=TASK,
        user_id=request.user_id,
        subject_id=request.subject_id,
        pipeline_run_id=run_id,
        prompt_version=prompt.version,
        attempt=attempt,
        system=prompt.text.replace(_NONCE_PLACEHOLDER, nonce),
        user="\n\n".join(parts),
        output_schema=OUTPUT_SCHEMA,
        payload={
            "command": request.command,
            "today": request.today.isoformat(),
            "titles": labels.titles,
        },
    )


# --- The model's output is checked by code ----------------------------------------------------


class OutputViolation(Exception):
    """The output broke rule `rule` (schema, kind, label, targets, until). Carries the rule only,
    never the output: it is logged."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


def _resolve(kind: str, fields: dict[str, Any], labels: Labels) -> dict[str, Any]:
    refs = REFS[kind]
    resolved = dict(fields)
    for name, label_kind in refs.items():
        value = fields.get(name)
        known = labels.ids[label_kind]
        if value is None:
            continue
        if isinstance(value, str):
            if value not in known:
                raise OutputViolation("label")
            resolved[name] = known[value]
        elif isinstance(value, list):
            items: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
            if not all(isinstance(item, str) and item in known for item in items):
                raise OutputViolation("label")
            if len(set(items)) != len(items):
                raise OutputViolation("targets")  # the same target twice
            resolved[name] = [known[item] for item in items]  # pyright: ignore[reportUnknownVariableType]
        else:
            raise OutputViolation("label")
    return resolved


def check_output(text: str, labels: Labels, today: datetime.date) -> Command:
    try:
        raw = json.loads(text)
    except ValueError:
        raise OutputViolation("schema") from None
    if not isinstance(raw, dict) or set(raw) != {"result"}:  # pyright: ignore[reportUnknownArgumentType]
        raise OutputViolation("schema")
    result: Any = raw["result"]  # pyright: ignore[reportUnknownVariableType]
    if not isinstance(result, dict):
        raise OutputViolation("schema")
    fields: dict[str, Any] = result  # pyright: ignore[reportUnknownVariableType]
    kind = fields.get("kind")
    if not isinstance(kind, str) or kind not in OPERATIONS:
        raise OutputViolation("kind")
    try:
        command = _ADAPTER.validate_python(_resolve(kind, fields, labels))
        check_dates(command, today)
    except ValidationError:
        raise OutputViolation("schema") from None
    except ValueError:
        raise OutputViolation("until") from None
    return command


# --- One parse --------------------------------------------------------------------------------


class ParseCommandInvalidError(Exception):
    """The output broke the rules twice, or once with no time to ask again: 502."""


def parse_command(
    request: ParseCommandRequest, *, llm: LlmClient, sessions: SessionFactory
) -> ParseCommandResponse:
    """Record the run, ask the model (twice at most, while time is left), check, answer."""
    deadline = time.monotonic() + DEADLINE_SECONDS
    prompt = load_prompt()
    run_id = _start_run(sessions, request, prompt)
    try:
        response = _ask_model(request, Labels.of(request), run_id, prompt, llm, deadline)
    except AuditUnavailableError:
        raise
    except ParseCommandInvalidError:
        _finish_run(sessions, run_id, "parse_command_invalid")
        raise
    except LlmUnavailableError:
        _finish_run(sessions, run_id, "llm_unavailable")
        raise
    except QuotaExceededError:
        _finish_run(sessions, run_id, "quota_exceeded")
        raise
    except Exception:
        with suppress(AuditUnavailableError):
            _finish_run(sessions, run_id, "internal_error")
        raise
    _finish_run(sessions, run_id, None)
    return response


def _ask_model(
    request: ParseCommandRequest,
    labels: Labels,
    run_id: uuid.UUID,
    prompt: Prompt,
    llm: LlmClient,
    deadline: float,
) -> ParseCommandResponse:
    nonce = new_nonce()
    for attempt in (1, 2):
        llm_request = build_llm_request(
            request, labels, run_id=run_id, attempt=attempt, nonce=nonce
        )
        result = llm.call(llm_request, deadline=deadline)
        try:
            command = check_output(result.text, labels, request.today)
        except OutputViolation as violation:
            _log.warning(
                "parse_command output refused",
                extra={
                    "outcome": violation.rule,
                    "attempt": attempt,
                    "llm_call_id": str(result.llm_call_id),
                },
            )
            if deadline - time.monotonic() < RETRY_MIN_SECONDS:
                break
            continue
        return ParseCommandResponse(
            provider=result.provider,
            model=result.model,
            prompt_version=prompt.version,
            run_id=run_id,
            llm_call_id=result.llm_call_id,
            result=command,
        )
    raise ParseCommandInvalidError


def _start_run(sessions: SessionFactory, request: ParseCommandRequest, prompt: Prompt) -> uuid.UUID:
    """Committed before any call: no paid call without its run."""
    run = PipelineRun(
        user_id=request.user_id,
        subject_id=request.subject_id,
        task=TASK,
        prompt_version=prompt.version,
        prompt_sha256=prompt.sha256,
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


# --- The fake parser (AI_LLM_PROVIDER=fake: local and test only) -------------------------------


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


_NUMBERS = re.compile(r"\d+")
_DANGEROUS = ("xóa", "xoá", "reset", "đặt lại", "trần chi phí", "tài khoản")


def _pick(titles: dict[str, str], prefix: str, numbers: list[str]) -> list[str]:
    return [f"{prefix}{n}" for n in numbers if f"{prefix}{n}" in titles]


def fake_parse(request: LlmRequest) -> str:
    """A deterministic parse of a few phrasings, shaped like a model's output (PLAN T9.1)."""
    payload = request.payload
    command = _norm(payload["command"])
    titles: dict[str, dict[str, str]] = payload["titles"]
    numbers = _NUMBERS.findall(command)

    def out(result: dict[str, Any]) -> str:
        return json.dumps({"result": result}, ensure_ascii=False)

    def unclear(reason: str) -> str:
        return out({"kind": "unclear", "reason": reason})

    if any(word in command for word in _DANGEROUS):
        return unclear("unsupported")
    if "gộp thẻ" in command:
        cards = _pick(titles["card"], "C", numbers)
        if len(cards) >= 2 and len(set(cards)) == len(cards):
            return out({"kind": "card_merge", "cards": cards})
        return unclear("unknown_target")
    if "đã học" in command or "chưa học" in command:
        sections = _pick(titles["section"], "S", numbers)
        if sections and len(set(sections)) == len(sections):
            return out(
                {
                    "kind": "section_mark",
                    "sections": sections,
                    "studied": "chưa học" not in command,
                }
            )
        return unclear("unknown_target")
    if "chỉ học môn" in command:
        today = datetime.date.fromisoformat(payload["today"])
        for label, title in titles["subject"].items():
            if _norm(title) in command:
                until = today + datetime.timedelta(days=6 - today.weekday())
                return out({"kind": "suggest_only_subject", "subject": label, "until": str(until)})
        return unclear("unknown_target")
    return unclear("ambiguous")
