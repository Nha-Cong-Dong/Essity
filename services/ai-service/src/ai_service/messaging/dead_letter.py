"""The dead letter (T4.3, ADR-0006): entries the consumer gave up on, kept for a person to read.

`events.dead` is shared with core-api's consumer and never trimmed (plan G4). Each entry holds
the original envelope as it arrived, the stream and id it came from, a reason and how many
times it was delivered (contracts/events/README.md). Never an exception message (ADR-0013):
the reason is a fixed code or an exception's class name.
"""

from redis import Redis
from redis.typing import EncodableT, FieldT

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
