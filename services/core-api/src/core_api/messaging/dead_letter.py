"""The dead letter stream `events.dead` (T4.4, ADR-0006): where an entry goes when it cannot be
handled, so it stops looping and can be looked at, and replayed, later.

An entry there holds the original `envelope` as it arrived, the `stream` and `entry_id` it came
from, a `reason` and how many `deliveries` it had (plan Y2). The reason is a code or an exception
class name, never the exception's message, which may hold data (ADR-0013). The stream has no
MAXLEN: nothing there may be trimmed before someone looks at it (plan G4).

By hand, inside the core-api container:

    python -m core_api.messaging.dead_letter purge --user <user uuid>

`purge` removes every entry that mentions the user, whatever its stream (T6.3 calls it when an
account is deleted: the dead letter keeps unit titles and file keys for ever otherwise).
"""

import argparse
import sys
import uuid
from collections.abc import Sequence
from typing import cast

from redis import Redis
from redis.typing import EncodableT, FieldT

DEAD_STREAM = "events.dead"

# Reasons that are not an exception class name.
INVALID_ENVELOPE = "invalid_envelope"
UNKNOWN_TYPE = "unknown_type"
USER_MISMATCH = "user_mismatch"
NO_HANDLER = "no_handler"
MAX_DELIVERIES_REACHED = "max_deliveries"


def dead_letter_and_ack(
    redis: Redis,
    *,
    stream: str,
    group: str,
    entry_id: bytes,
    envelope: bytes,
    reason: str,
    deliveries: int,
    dead_stream: str = DEAD_STREAM,
) -> None:
    """Copy the entry to `dead_stream` and acknowledge it in `stream`, both or neither (MULTI)."""
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


def purge_user(redis: Redis, *, dead_stream: str, user_id: uuid.UUID) -> int:
    """Delete every dead entry whose envelope mentions `user_id`, from any stream; return how many.

    Anywhere in the bytes, in any case: as the envelope's user, and also in an object key of an
    event someone else sent (user_mismatch), or in an entry that broke the contract. Removing a
    stranger's entry along with it costs a replay nobody needed; keeping the user's data does not
    meet T6.3.
    """
    needle = str(user_id).encode()
    entries = cast(list[tuple[bytes, dict[bytes, bytes]]], redis.xrange(dead_stream))
    doomed = [
        entry_id for entry_id, fields in entries if needle in fields.get(b"envelope", b"").lower()
    ]
    if doomed:
        redis.xdel(dead_stream, *doomed)
    return len(doomed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core_api.messaging.dead_letter")
    parser.add_argument("--dead-stream", default=DEAD_STREAM, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)
    purge_parser = commands.add_parser("purge", help="delete every entry of one user")
    purge_parser.add_argument("--user", required=True, type=uuid.UUID)
    args = parser.parse_args(argv)

    from core_api.clients.redis import redis_from_url
    from core_api.config import get_settings

    redis = redis_from_url(get_settings().redis_url.get_secret_value())
    print(f"purged {purge_user(redis, dead_stream=args.dead_stream, user_id=args.user)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
