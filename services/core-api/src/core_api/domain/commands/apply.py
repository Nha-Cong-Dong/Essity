"""Apply a command: all-or-nothing, inverse and diff taken from the starting snapshot (AC4, AC9)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from core_api.domain.commands.inverse import Change, Revert, build_inverse, diff
from core_api.domain.commands.registry import CommandRejected, IdSource, Op, run_op
from core_api.domain.commands.state import Snapshot

LARGE_COMMAND_ITEMS = 10


@dataclass(frozen=True)
class LoggedCommand:
    """What `command_log` keeps (AC9): ops, diff, inverse; `undone` flips once on undo."""

    command_id: uuid.UUID
    session_id: uuid.UUID
    ops: tuple[Op, ...]
    changes: tuple[Change, ...]
    inverse: tuple[Revert, ...]
    undone: bool = False

    @property
    def affected(self) -> int:
        return len(self.changes)


@dataclass(frozen=True)
class ApplyResult:
    state: Snapshot
    entry: LoggedCommand

    @property
    def affected(self) -> int:
        return self.entry.affected


def apply_command(
    state: Snapshot,
    ops: Sequence[Op],
    ids: IdSource,
    *,
    command_id: uuid.UUID,
    session_id: uuid.UUID,
) -> ApplyResult:
    """Run `ops` in order; any rejection raises and the caller's `state` is untouched.

    More than `LARGE_COMMAND_ITEMS` affected items still run; the count is in `affected`.
    """
    if not ops:
        raise CommandRejected("empty_command")
    current = state
    for op in ops:
        current = run_op(current, op, ids)
    changes = diff(state, current)
    entry = LoggedCommand(command_id, session_id, tuple(ops), changes, build_inverse(changes))
    return ApplyResult(current, entry)
