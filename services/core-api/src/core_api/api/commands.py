"""`POST /v1/commands` and `POST /v1/commands/{command_id}/undo` (T9.2e, US-18, ADR-0030).

The command bar's two calls. A command comes as a line of text (the parser reads it, cut at 8 s,
once) or as ops the client parsed; either way the same validator and the same apply as the
screens' own writes (`CommandService`). `command_id` is the client's: a retry with the same
request answers with the stored result and does not parse again.

Answers (the `detail` is a stable code, never text of the command):
- 200: applied, or the stored answer of a retry; `status: "unclear"` when the parser did not
  understand (nothing ran, nothing was logged).
- 403 email_not_verified (US-12 AC2).
- 404 not_owned (an id is not this user's, or no such command), subject_not_found.
- 409 command_id_reused (the id came with another request); changed_after, not_latest,
  other_session, conflict, nothing_to_undo (undo refused).
- 422 unsupported, empty_command, ...: the command cannot run (a code of `CommandRejected`).
- 429 quota_hard_cap: the AI budget is spent; web turns the command bar off (AC8), editing by
  hand still works.
- 502 parse_invalid: the parser's answer broke its rules.
- 503 ai_disabled, parse_unavailable: the parser is off, or did not answer within 8 s.
"""

import uuid
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal, NoReturn, cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.ping import get_ai_client
from core_api.api.text import storable_answer, storable_text
from core_api.clients.ai_client import AiServiceClient, NotGraded
from core_api.db.session import DbSession
from core_api.domain.commands.registry import CommandRejected
from core_api.repositories.subject import SubjectRepository
from core_api.services.command_context import build_parse_payload
from core_api.services.commands import (
    ApplyOutcome,
    CommandIdReused,
    CommandRequest,
    CommandService,
)
from core_api.services.suggestions import learning_today

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

Ai = Annotated[AiServiceClient, Depends(get_ai_client)]

MAX_COMMAND_CHARS = 500  # the parser's own limit
MAX_CLIENT_OPS = 50

_AS_MISSING = {"not_owned"}
_AS_CONFLICT = {
    "changed_after",
    "not_latest",
    "other_session",
    "conflict",
    "nothing_to_undo",
    "id_collision",
    "unitchangedelsewhere",  # a screen saved the card first: the client may retry
}
_UNCLEAR_REASONS = ("ambiguous", "unknown_target", "unsupported", "missing_info")
type UnclearReason = Literal["ambiguous", "unknown_target", "unsupported", "missing_info"]


def storable_ops(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every string in the ops (keys too) is text Postgres can keep: the ops go into the log's
    jsonb and, as card or answer text, into the tables. The text of a card keeps its lines."""

    def walk(value: object) -> None:
        if isinstance(value, str):
            storable_answer(value)
        elif isinstance(value, dict):
            for key, item in cast(dict[object, object], value).items():
                walk(key)
                walk(item)
        elif isinstance(value, list):
            for item in cast(list[object], value):
                walk(item)

    walk(ops)
    return ops


class CommandIn(BaseModel):
    """One of `text` (the parser reads it, in `subject_id`'s context) or `ops` (already parsed)."""

    model_config = ConfigDict(extra="forbid")

    command_id: uuid.UUID
    screen_session_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    text: (
        Annotated[
            str,
            StringConstraints(min_length=1, max_length=MAX_COMMAND_CHARS),
            AfterValidator(storable_text),
        ]
        | None
    ) = None
    ops: (
        Annotated[
            list[dict[str, Any]],
            Field(min_length=1, max_length=MAX_CLIENT_OPS),
            AfterValidator(storable_ops),
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def _one_source(self) -> "CommandIn":
        if (self.text is None) == (self.ops is None):
            raise ValueError("exactly one of text, ops")
        if self.text is not None and (not self.text.strip() or self.subject_id is None):
            raise ValueError("text needs a non-blank line and a subject_id")
        return self


class DiffItemOut(BaseModel):
    kind: str
    id: str | None
    verb: str
    before: Any
    after: Any


class CommandOut(BaseModel):
    command_id: uuid.UUID
    status: Literal["applied", "undone"]
    diff: list[DiffItemOut]
    affected: int
    op_kinds: list[str]
    replayed: bool


class UnclearOut(BaseModel):
    """The parser did not understand: nothing ran and nothing was logged (AC3)."""

    status: Literal["unclear"] = "unclear"
    reason: UnclearReason


class UndoOut(BaseModel):
    command_id: uuid.UUID
    status: Literal["undone"]
    diff: list[DiffItemOut]
    affected: int
    replayed: bool


class _Unclear(Exception):
    def __init__(self, reason: UnclearReason) -> None:
        super().__init__(reason)
        self.reason: UnclearReason = reason


def _fail(code: int, detail: str) -> NoReturn:
    raise HTTPException(status_code=code, detail=detail)


def refusal(error: CommandRejected) -> HTTPException:
    if error.code in _AS_MISSING:
        return HTTPException(status_code=404, detail=error.code)
    if error.code in _AS_CONFLICT:
        return HTTPException(status_code=409, detail=error.code)
    return HTTPException(status_code=422, detail=error.code)


def _parse_failed(failure: NotGraded) -> NoReturn:
    match failure.failure:
        case "quota":
            _fail(429, "quota_hard_cap")
        case "disabled":
            _fail(503, "ai_disabled")
        case "invalid":
            _fail(502, "parse_invalid")
        case _:
            _fail(503, "parse_unavailable")


def _reason_of(value: object) -> UnclearReason:
    for known in _UNCLEAR_REASONS:
        if value == known:
            return known
    return "ambiguous"


@router.post("/commands")
def apply_command(
    body: CommandIn, user: VerifiedUser, session: DbSession, ai: Ai, now: Now
) -> CommandOut | UnclearOut:
    """Apply a command, once per `command_id`. The service commits a read-only transaction before
    it parses, so nothing of the command is written before this call (the sliding of the sign-in
    session is the only write that can precede it, and that commit keeps it)."""
    subject_id = body.subject_id

    def parse(text: str) -> Sequence[Mapping[str, Any]]:
        assert subject_id is not None
        if SubjectRepository(session, user.id).get(subject_id) is None:
            _fail(404, "subject_not_found")
        payload = build_parse_payload(session, user.id, subject_id, text, learning_today(user, now))
        session.commit()  # the reads above end here: no transaction stays open for 8 s of AI
        reply = ai.parse_command(jsonable_encoder(payload))
        if isinstance(reply, NotGraded):
            _parse_failed(reply)
        result = reply.result
        if result.get("kind") == "unclear":
            raise _Unclear(_reason_of(result.get("reason")))
        return [result]

    request = CommandRequest(body.text or "", body.ops)
    try:
        outcome = CommandService(session, user.id).apply(
            body.command_id, body.screen_session_id, request, parse=parse, now=now
        )
    except _Unclear as unclear:
        return UnclearOut(reason=unclear.reason)
    except CommandIdReused:
        raise HTTPException(status_code=409, detail="command_id_reused") from None
    except CommandRejected as error:
        raise refusal(error) from None
    return _out(outcome)


@router.post("/commands/{command_id}/undo")
def undo_command(
    command_id: uuid.UUID, user: VerifiedUser, session: DbSession, now: Now
) -> UndoOut:
    try:
        outcome = CommandService(session, user.id).undo(command_id, now=now)
    except CommandRejected as error:
        raise refusal(error) from None
    return UndoOut(
        command_id=outcome.command_id,
        status="undone",
        diff=[DiffItemOut(**item) for item in outcome.diff],
        affected=outcome.affected,
        replayed=outcome.replayed,
    )


def _out(outcome: ApplyOutcome) -> CommandOut:
    return CommandOut(
        command_id=outcome.command_id,
        status="undone" if outcome.status == "undone" else "applied",
        diff=[DiffItemOut(**item) for item in outcome.diff],
        affected=outcome.affected,
        op_kinds=outcome.op_kinds,
        replayed=outcome.replayed,
    )
