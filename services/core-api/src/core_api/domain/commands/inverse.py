"""Diff and inverse of a command (ADR-0030: `inverse_json` is computed before the change lands).

The inverse is built from the snapshot a command started from and the state it produced, never
from reading the stored state afterwards. For each record the command touched it keeps the
before-image and the `rev` the command left behind (`expected_rev`): undo refuses when that
`rev` has moved on.
"""

import uuid
from dataclasses import dataclass

from core_api.domain.commands.state import Key, Record, Snapshot


@dataclass(frozen=True)
class Change:
    kind: str
    id: uuid.UUID
    before: Record | None
    after: Record | None


@dataclass(frozen=True)
class Revert:
    kind: str
    id: uuid.UUID
    before: Record | None  # None: the command created the record
    expected_rev: int | None  # None: the command removed the record


def diff(before: Snapshot, after: Snapshot) -> tuple[Change, ...]:
    keys: list[Key] = [k for k in after.records if before.records.get(k) != after.records[k]]
    keys += [k for k in before.records if k not in after.records]
    return tuple(
        Change(k[0], k[1], before.records.get(k), after.records.get(k))
        for k in sorted(keys, key=lambda k: (k[0], str(k[1])))
    )


def build_inverse(changes: tuple[Change, ...]) -> tuple[Revert, ...]:
    return tuple(
        Revert(c.kind, c.id, c.before, c.after.rev if c.after is not None else None)
        for c in changes
    )
