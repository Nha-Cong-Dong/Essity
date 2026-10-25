"""The dead letter (T4.3, ADR-0006): entries the consumer gave up on, kept for a person to read.

`events.dead` is shared with core-api's consumer and never trimmed (plan G4). Each entry holds
the original envelope as it arrived, the stream and id it came from, a reason and how many
times it was delivered (contracts/events/README.md). Never an exception message (ADR-0013):
the reason is a fixed code or an exception's class name.

By hand, inside the ai-service container:

    python -m ai_service.messaging.dead_letter list
    python -m ai_service.messaging.dead_letter replay <dead entry id>... | --all
    python -m ai_service.messaging.dead_letter purge --user <user uuid>

`list` and `replay` only touch entries that came from `events.core`: the rest are core-api's.
`replay` puts the original envelope back on its stream and removes it from the dead letter; the
consumer skips an event it has already handled, and one that fails again comes back here, so a
replay never loops. `purge` removes every entry of one user whatever its stream (T6.3 calls it
when an account is deleted: the dead letter keeps unit titles and file keys for ever otherwise).
"""

import argparse
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from pydantic import ValidationError
from redis import Redis
from redis.typing import EncodableT, FieldT

from ai_service.messaging.envelope import parse_event

DEAD_STREAM = "events.dead"
SOURCE_STREAM = "events.core"
# As the relay trims events.core (plan E3).
STREAM_MAXLEN = 100_000

# Reasons that are not an exception's class name.
INVALID_ENVELOPE = "invalid_envelope"
UNKNOWN_TYPE = "unknown_type"
USER_MISMATCH = "user_mismatch"
NO_HANDLER = "no_handler"
MAX_DELIVERIES = "max_deliveries"


def send_to_dead(
    redis: Redis,
    *,
    dead_stream: str,
    stream: str,
    group: str,
    entry_id: str,
    envelope: str,
    reason: str,
    deliveries: int,
) -> None:
    """Copy the entry to the dead letter and acknowledge it, both or neither (MULTI)."""
    fields: dict[FieldT, EncodableT] = {
        "envelope": envelope,
        "stream": stream,
        "entry_id": entry_id,
        "reason": reason,
        "deliveries": deliveries,
    }
    # redis-py leaves Pipeline's type parameter unknown.
    pipeline = redis.pipeline(transaction=True)  # pyright: ignore[reportUnknownMemberType]
    pipeline.xadd(dead_stream, fields)
    pipeline.xack(stream, group, entry_id)
    pipeline.execute()


@dataclass(frozen=True)
class DeadEntry:
    id: str
    fields: dict[str, str]

    @property
    def envelope(self) -> str:
        return self.fields.get("envelope", "")

    @property
    def stream(self) -> str:
        return self.fields.get("stream", "")


def _entries(redis: Redis, dead_stream: str) -> list[DeadEntry]:
    rows = cast(list[tuple[str, dict[str, str]]], redis.xrange(dead_stream))
    return [DeadEntry(entry_id, fields) for entry_id, fields in rows]


def describe(entry: DeadEntry) -> str:
    """One line: ids, type, reason and count, never the payload. The event's id and type only
    when the envelope passes the contract: otherwise they are any text."""
    try:
        event = parse_event(entry.envelope)
        event_id, event_type = str(event.event_id), event.event_type
    except ValidationError:
        event_id, event_type = "-", "-"
    reason = entry.fields.get("reason", "-")[:64]
    deliveries = entry.fields.get("deliveries", "-")[:8]
    return f"{entry.id}\t{event_id}\t{event_type}\t{reason}\t{deliveries}"


def list_entries(redis: Redis, *, dead_stream: str, stream: str) -> list[DeadEntry]:
    """The dead entries that came from `stream`, oldest first."""
    return [entry for entry in _entries(redis, dead_stream) if entry.stream == stream]


def replay(redis: Redis, *, dead_stream: str, stream: str, ids: Sequence[str] | None = None) -> int:
    """Put entries from `stream` back on it (all of them, or those in `ids`); return how many.

    Each one moves in a MULTI: XADD to `stream` and XDEL from the dead letter, both or neither.
    Entries without an envelope stay (review 🟡7): there is nothing to replay.
    """
    wanted = set(ids) if ids is not None else None
    moved = 0
    for entry in list_entries(redis, dead_stream=dead_stream, stream=stream):
        if (wanted is not None and entry.id not in wanted) or not entry.envelope:
            continue
        fields: dict[FieldT, EncodableT] = {"envelope": entry.envelope}
        pipeline = redis.pipeline(transaction=True)  # pyright: ignore[reportUnknownMemberType]
        pipeline.xadd(stream, fields, maxlen=STREAM_MAXLEN, approximate=True)
        pipeline.xdel(dead_stream, entry.id)
        pipeline.execute()
        moved += 1
    return moved


def purge_user(redis: Redis, *, dead_stream: str, user_id: uuid.UUID) -> int:
    """Delete every dead entry whose envelope mentions `user_id`, from any stream; return how many.

    Anywhere in the text, in any case (review 🟢E): as the envelope's user, and also in an
    object key of an event someone else sent (user_mismatch), or in an entry that broke the
    contract. Removing a stranger's entry along with it costs a replay nobody needed; keeping
    the user's data does not meet T6.3.
    """
    needle = str(user_id)
    doomed = [
        entry.id for entry in _entries(redis, dead_stream) if needle in entry.envelope.lower()
    ]
    if doomed:
        redis.xdel(dead_stream, *doomed)
    return len(doomed)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ai_service.messaging.dead_letter")
    parser.add_argument("--stream", default=SOURCE_STREAM, help=argparse.SUPPRESS)
    parser.add_argument("--dead-stream", default=DEAD_STREAM, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="dead entries from events.core, without their payload")
    replay_parser = commands.add_parser("replay", help="put entries back on events.core")
    replay_parser.add_argument("ids", nargs="*", help="dead entry ids, as `list` prints them")
    replay_parser.add_argument("--all", action="store_true")
    purge_parser = commands.add_parser("purge", help="delete every entry of one user")
    purge_parser.add_argument("--user", required=True, type=uuid.UUID)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "replay" and bool(args.all) == bool(args.ids):
        parser.error("replay needs dead entry ids or --all, not both")

    from ai_service.clients.redis import redis_from_url
    from ai_service.config import get_settings

    url = get_settings().redis_url
    if url is None:
        sys.exit("AI_REDIS_URL is not set")
    redis = redis_from_url(url.get_secret_value())
    stream: str = args.stream
    dead_stream: str = args.dead_stream
    if args.command == "list":
        for entry in list_entries(redis, dead_stream=dead_stream, stream=stream):
            print(describe(entry))
    elif args.command == "replay":
        ids: list[str] | None = None if args.all else list(args.ids)
        moved = replay(redis, dead_stream=dead_stream, stream=stream, ids=ids)
        print(f"replayed {moved}")
    else:
        print(f"purged {purge_user(redis, dead_stream=dead_stream, user_id=args.user)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
