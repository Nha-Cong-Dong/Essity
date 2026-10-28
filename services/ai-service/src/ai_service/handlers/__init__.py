"""Handlers of the events ai-service receives on `events.core`, by event type (T4.3).

Empty until T4.7 (`document.uploaded.v1`) and the tasks after it add theirs. Until then the
consumer sends every event to the dead letter as `no_handler`, from where it can be replayed
once its handler exists. See `ai_service.messaging.consumer.Handler` for what a handler may do.
"""

from ai_service.messaging.consumer import Handler

HANDLERS: dict[str, Handler] = {}
