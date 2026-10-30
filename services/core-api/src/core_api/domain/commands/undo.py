"""Undo: newest not-yet-undone command first, refused when anything it touched moved on (AC5)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace

from core_api.domain.commands.apply import LoggedCommand
from core_api.domain.commands.inverse import Change, diff
from core_api.domain.commands.registry import CommandRejected
from core_api.domain.commands.state import Card, CardStatus, Snapshot


@dataclass(frozen=True)
class UndoResult:
    state: Snapshot
    entry: LoggedCommand  # the logged command, now `undone`
    changes: tuple[Change, ...]

    @property
    def affected(self) -> int:
        return len(self.changes)


def newest_open(log: Sequence[LoggedCommand]) -> LoggedCommand | None:
    return next((e for e in reversed(log) if not e.undone), None)


def undo_latest(state: Snapshot, log: Sequence[LoggedCommand], session_id: uuid.UUID) -> UndoResult:
    """Undo the newest open command of this screen session; raise `CommandRejected` otherwise.

    Codes: `nothing_to_undo`, `other_session`, `changed_after` (detail names the record).
    Records the command created are not deleted: a card becomes discarded, with a new rev.
    A canonical card the command edited gets its old text back as a new rev (append-only).
    """
    entry = newest_open(log)
    if entry is None:
        raise CommandRejected("nothing_to_undo")
    if entry.session_id != session_id:
        raise CommandRejected("other_session")
    for revert in entry.inverse:
        current = state.get(revert.kind, revert.id)
        if (None if current is None else current.rev) != revert.expected_rev:
            raise CommandRejected("changed_after", f"{revert.kind} {revert.id}")
    out = state
    for revert in entry.inverse:
        current = state.get(revert.kind, revert.id)
        if revert.before is not None:
            out = out.put(replace(revert.before, rev=(current.rev if current else 0) + 1))
        elif isinstance(current, Card):
            out = out.put(current.changed(status=CardStatus.DISCARDED))
        elif current is not None:
            out = out.drop((revert.kind, revert.id))  # a filter the command created
    return UndoResult(out, replace(entry, undone=True), diff(state, out))
