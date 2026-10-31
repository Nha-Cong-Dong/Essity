"""Handlers of the events ai-service receives on `events.core`, by event type (T4.3).

`document.uploaded.v1` is T4.7's, `grade.requested.v1` T4.19's and `session.confirmed.v1`
T4.16b's; the tasks after them add theirs. An event type without a handler goes to the dead
letter as `no_handler`, from where it can be replayed once there is one. See
`ai_service.messaging.consumer.Handler` for what a handler may do.
"""

from redis import Redis

from ai_service.clients.storage import ObjectStorage
from ai_service.db.session import SessionFactory
from ai_service.llm.client import LlmClient
from ai_service.messaging.consumer import Handler
from ai_service.tasks.grade_async import GradeAsync
from ai_service.tasks.index_document import IndexDocument
from ai_service.tasks.process_session import ProcessSession


def build_handlers(
    *,
    redis: Redis,
    storage: ObjectStorage,
    llm: LlmClient | None,
    sessions: SessionFactory,
) -> dict[str, Handler]:
    return {
        "document.uploaded.v1": IndexDocument(
            storage=storage, redis=redis, llm=llm, sessions=sessions
        ),
        "grade.requested.v1": GradeAsync(storage=storage, redis=redis, llm=llm, sessions=sessions),
        "session.confirmed.v1": ProcessSession(
            storage=storage, redis=redis, llm=llm, sessions=sessions
        ),
    }
