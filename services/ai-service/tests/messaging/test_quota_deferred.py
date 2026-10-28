"""T2.11: a handler over the soft quota is deferred by the consumer, never dead-lettered."""

from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ai_service.llm.quota import QuotaExceededError
from tests.messaging.conftest import Names
from tests.messaging.helpers import DOCUMENT_UPLOADED, Recorder, publish, uploaded
from tests.messaging.test_consumer import make_consumer, pending
from tests.messaging.test_failures import dead_entries


def test_t211_soft_quota_in_a_handler_defers_the_event(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: the handler has to remember to catch the quota error itself, and one that
    # forgets sends the event to the dead letter after five tries.
    publish(redis_client, names.stream, uploaded())
    recorder = Recorder(fail_with=lambda: QuotaExceededError(hard=False, window="day"))
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    for _ in range(7):
        assert consumer.run_once() == ["deferred"]
    assert dead_entries(redis_client, names) == []
    assert pending(redis_client, names) == 1
