"""T4.3: `processed_event` records the events a consumer has handled (ADR-0006, at least once).

Runs on the real test PostgreSQL. Each test uses a consumer name of its own, so rows from other
tests never collide.
"""

import threading
import uuid

from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session

from ai_service.db.models import ProcessedEvent
from ai_service.messaging.idempotency import claim, was_processed


def consumer_name() -> str:
    return f"test-{uuid.uuid4()}"


def test_t43_first_claim_wins_and_second_is_a_duplicate(engine: Engine) -> None:
    # Red when: claim does not record the event, and a redelivered event runs its handler again.
    consumer, event_id = consumer_name(), uuid.uuid4()
    with Session(engine) as session, session.begin():
        assert claim(session, consumer, event_id) is True
    with Session(engine) as session, session.begin():
        assert claim(session, consumer, event_id) is False


def test_t43_claim_is_per_consumer(engine: Engine) -> None:
    # Two consumer groups reading the same event each handle it once.
    event_id = uuid.uuid4()
    with Session(engine) as session, session.begin():
        assert claim(session, consumer_name(), event_id) is True
        assert claim(session, consumer_name(), event_id) is True


def test_t43_rolled_back_claim_leaves_no_row(engine: Engine) -> None:
    # Red when: claim commits on its own, and a handler that failed is never retried.
    consumer, event_id = consumer_name(), uuid.uuid4()
    with Session(engine) as session:
        session.begin()
        assert claim(session, consumer, event_id) is True
        session.rollback()
    with Session(engine) as session:
        assert (
            session.scalar(select(ProcessedEvent).where(ProcessedEvent.consumer == consumer))
            is None
        )
    with Session(engine) as session, session.begin():
        assert claim(session, consumer, event_id) is True


def test_t43_claim_concurrent_second_waits_for_first_commit(engine: Engine) -> None:
    # Red when: claim checks then inserts (no ON CONFLICT), or raises on the conflict: the second
    # transaction must wait for the first and then see a duplicate, never run the handler too.
    consumer, event_id = consumer_name(), uuid.uuid4()
    first_claimed = threading.Event()
    release_first = threading.Event()
    results: dict[str, bool] = {}

    def first() -> None:
        with Session(engine) as session, session.begin():
            results["first"] = claim(session, consumer, event_id)
            first_claimed.set()
            release_first.wait(5)

    thread = threading.Thread(target=first)
    thread.start()
    assert first_claimed.wait(5)

    second_done = threading.Event()

    def second() -> None:
        with Session(engine) as session, session.begin():
            results["second"] = claim(session, consumer, event_id)
        second_done.set()

    other = threading.Thread(target=second)
    other.start()
    # The second claim is blocked on the first one's uncommitted row.
    assert not second_done.wait(0.5)
    release_first.set()
    thread.join(5)
    other.join(5)
    assert results == {"first": True, "second": False}


def test_t43_was_processed_sees_committed_claims_only(engine: Engine) -> None:
    # Review 🟡4: an entry delivered too often is checked here before it is dead-lettered.
    consumer, event_id = consumer_name(), uuid.uuid4()
    with Session(engine) as session:
        assert was_processed(session, consumer, event_id) is False
    with Session(engine) as session:
        session.begin()
        claim(session, consumer, event_id)
        session.rollback()
        assert was_processed(session, consumer, event_id) is False
    with Session(engine) as session, session.begin():
        claim(session, consumer, event_id)
    with Session(engine) as session:
        assert was_processed(session, consumer, event_id) is True


def test_t43_processed_event_holds_no_user_data(engine: Engine) -> None:
    # The table keeps ids only: nothing here for T6.3 to delete when a user goes.
    columns = {column["name"] for column in inspect(engine).get_columns("processed_event")}
    assert columns == {"consumer", "event_id", "processed_at"}
