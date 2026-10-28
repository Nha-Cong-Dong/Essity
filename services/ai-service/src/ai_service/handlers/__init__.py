"""Handlers of the events ai-service receives on `events.core`, by event type (T4.3).

`document.uploaded.v1` is T4.7's; the tasks after it add theirs. An event type without a
handler goes to the dead letter as `no_handler`, from where it can be replayed once there is
one. See `ai_service.messaging.consumer.Handler` for what a handler may do.
"""

from redis import Redis

from ai_service.clients.storage import ObjectStorage
from ai_service.messaging.consumer import Handler
from ai_service.tasks.index_document import IndexDocument


def build_handlers(*, redis: Redis, storage: ObjectStorage) -> dict[str, Handler]:
    return {"document.uploaded.v1": IndexDocument(storage=storage, redis=redis)}
