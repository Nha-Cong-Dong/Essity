"""Pure helpers of the command service (T9.2c): the request hash, the one validator of ops (the
client's and the LLM's alike) and the JSON of ops and records.

Nothing here may carry free text into a log or an error: `CommandRejected.detail` out of this
module holds only a registered op kind, an id or a count (ADR-0013, plan P6).
"""

import datetime
import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from core_api.domain.commands.registry import CommandRejected, Op, kind_of, op_from_json
from core_api.domain.commands.state import Record

# The ops a command may run. `section_set_pages` (it reweighs the whole document) and
# `question_relink` (a many-to-many link set has no revision) are in the domain registry but have
# no undo, so they are not offered here (plan decisions 02/11).
APPLICABLE_KINDS = frozenset(
    {
        "card_edit",
        "card_merge",
        "card_split",
        "card_add",
        "card_discard_draft",
        "card_add_idea",
        "section_exclude",
        "section_mark",
        "suggest_only_subject",
        "suggest_defer_subject",
        "question_set_type",
        "question_set_answer",
        "question_remove_from_practice",
    }
)
MAX_OPS = 50
MAX_TEXT = 5000
_KIND_SHAPE = re.compile(r"[a-z_]{1,40}")


def payload_hash(
    raw_text: str, session_id: uuid.UUID, ops: Sequence[Mapping[str, Any]] | None
) -> str:
    """SHA-256 (hex) of the request as received, before any parse: raw text in NFC (not
    trimmed), the screen session, the client's ops or null. Never the `command_id`."""
    body = {
        "raw_text": unicodedata.normalize("NFC", raw_text),
        "screen_session_id": str(session_id).lower(),
        "ops": None if ops is None else [dict(o) for o in ops],
    }
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def validate_ops(raw: Sequence[Mapping[str, Any]]) -> list[Op]:
    """Ops from JSON, whoever sent them: a kind outside `APPLICABLE_KINDS` (or `unclear`), an
    unknown field, a bad id, too many ops or too long a text is `CommandRejected`."""
    if not raw:
        raise CommandRejected("empty_command")
    if len(raw) > MAX_OPS:
        raise CommandRejected("too_many_ops", str(len(raw)))
    ops: list[Op] = []
    for item in raw:
        kind = item.get("kind") if isinstance(item, Mapping) else None  # pyright: ignore[reportUnnecessaryIsInstance]
        if not isinstance(kind, str) or kind not in APPLICABLE_KINDS:
            shown = kind if isinstance(kind, str) and _KIND_SHAPE.fullmatch(kind) else ""
            raise CommandRejected("unsupported", shown)
        for value in item.values():
            if isinstance(value, str) and len(value) > MAX_TEXT:
                raise CommandRejected("text_too_long", kind)
        try:
            ops.append(op_from_json(dict(item)))
        except CommandRejected as error:
            raise CommandRejected(error.code, kind) from None
    return ops


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def op_to_json(op: Op) -> dict[str, Any]:
    """`{"kind": ..., fields}`: what `op_from_json` reads back."""
    assert is_dataclass(op)
    out: dict[str, Any] = {"kind": kind_of(op)}
    for f in fields(op):
        out[f.name] = _plain(getattr(op, f.name))
    return out


def record_to_json(record: Record | None) -> dict[str, Any] | None:
    if record is None:
        return None
    assert is_dataclass(record)
    return {f.name: _plain(getattr(record, f.name)) for f in fields(record) if f.name != "user_id"}
