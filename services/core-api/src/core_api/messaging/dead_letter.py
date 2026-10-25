"""The dead letter stream `events.dead` (T4.4, ADR-0006): where an entry goes when it cannot be
handled, so it stops looping and can be looked at, and replayed, later.

An entry there holds the original `envelope` as it arrived, the `stream` and `entry_id` it came
from, a `reason` and how many `deliveries` it had (plan Y2). The reason is a code or an exception
class name, never the exception's message, which may hold data (ADR-0013). The stream has no
MAXLEN: nothing there may be trimmed before someone looks at it (plan G4).
"""

from redis import Redis
from redis.typing import EncodableT, FieldT

DEAD_STREAM = "events.dead"

# Reasons that are not an exception class name.
INVALID_ENVELOPE = "invalid_envelope"
UNKNOWN_TYPE = "unknown_type"
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
