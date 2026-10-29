"""T4.19 (US-05): grading through the queue. A synchronous grading that fails for a reason that may
clear goes to `grade.requested.v1`; the handler of `grade.completed.v1` writes the grade with the
same `record_grade` as T2.13. Storage is a double; the database is real."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t213_grade_attempt import Desk, Stub

from core_api.api.attempts import attempt_view
from core_api.clients.ai_client import Graded, NotGraded
from core_api.clients.storage import StorageUnavailableError
from core_api.db.models import Grade, GradeUnit, Outbox, ReviewLog, User
from core_api.handlers.grade_completed import GradingBusyError, OnGradeCompleted
from core_api.messaging.envelope import Event, parse_event
from core_api.repositories.grade_job import GradeJobRepository
from fake_storage import FakeStorage

NOW = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)
UNAVAILABLE = NotGraded("unavailable", "timeout")


@pytest.fixture
def desk(db_session: Session, two_users: tuple[User, User]) -> Desk:
    return Desk(db_session, two_users[0], units=2)


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


def queue(  # noqa: ANN201
    desk: Desk,
    storage: FakeStorage | None,
    stub: Stub | None = None,
    *,
    attempt: uuid.UUID | None = None,
) -> tuple[uuid.UUID, Any]:
    """Grade an attempt (a new one by default) with a grader that is down unless `stub` says."""
    from core_api.grading import grade_attempt

    attempt = attempt or desk.submitted("Câu trả lời của tôi")
    stub = stub or Stub(failure=UNAVAILABLE)
    outcome = grade_attempt(
        desk.session, desk.user, attempt, stub, environment="production", storage=storage, now=NOW
    )
    return attempt, outcome


def requested(desk: Desk) -> list[Outbox]:
    return list(
        desk.session.scalars(
            select(Outbox).where(
                Outbox.event_type == "grade.requested.v1", Outbox.user_id == desk.user.id
            )
        )
    )


def completed_event(user: User, attempt: uuid.UUID, key: str) -> Event:
    return parse_event(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "grade.completed.v1",
                "schema_version": 1,
                "occurred_at": "2026-10-28T08:01:00.000000Z",
                "user_id": str(user.id),
                "trace_context": {},
                "payload": {"attempt_id": str(attempt), "result_key": key},
            }
        )
    )


def answered(desk: Desk, storage: FakeStorage, request_key: str, **response: Any) -> str:
    """ai-service's result file for a request, as it writes it; returns its key."""
    request = json.loads(storage.objects[request_key][0])
    graded = Stub().grade(request)
    assert isinstance(graded, Graded)
    body = graded.response.model_dump(mode="json") | response
    key = request_key.replace("/request-", "/result-")
    storage.write(
        key, json.dumps({"status": "graded", "response": body}).encode(), content_type="x"
    )
    return key


def handler(storage: FakeStorage, environment: str = "test") -> OnGradeCompleted:
    return OnGradeCompleted(storage, environment=environment, clock=lambda: NOW)


def queued(desk: Desk, storage: FakeStorage) -> tuple[uuid.UUID, str]:
    attempt, outcome = queue(desk, storage)
    assert outcome.grading == "in_progress"
    return attempt, requested(desk)[0].payload["request_key"]


def view(desk: Desk, attempt: uuid.UUID):  # noqa: ANN201
    from core_api.repositories.review import AttemptRepository

    found = AttemptRepository(desk.session, desk.user.id).get(attempt)
    assert found is not None
    return attempt_view(desk.session, desk.user.id, found, None, now=NOW)


# --- The way in: the synchronous grading fails ---------------------------------------------------


def test_a_failed_call_queues_the_request_and_answers_in_progress(
    desk: Desk, storage: FakeStorage
) -> None:
    attempt, outcome = queue(desk, storage)
    assert (outcome.grading, outcome.failure) == ("in_progress", None)
    assert desk.count(Grade) == 0

    (row,) = requested(desk)
    assert row.payload["attempt_id"] == str(attempt)
    key = row.payload["request_key"]
    assert key.startswith(f"users/{desk.user.id}/grading/{attempt}/request-")
    # The request is the body of /v1/grade, in a file: the answer is not in the event.
    sent = json.loads(storage.objects[key][0])
    assert sent["answer"] == "Câu trả lời của tôi" and sent["attempt_id"] == str(attempt)
    assert "Câu trả lời của tôi" not in json.dumps(row.payload)

    job = GradeJobRepository(desk.session, desk.user.id).for_attempt(attempt)
    assert job is not None and (job.status, job.failure) == ("queued", None)
    shown = view(desk, attempt)
    assert (shown.grading, shown.result) == ("in_progress", None)


def test_regrade_while_queued_does_not_ask_the_ai_or_queue_again(
    desk: Desk, storage: FakeStorage
) -> None:
    attempt, _ = queue(desk, storage)
    again = Stub()
    _, outcome = queue(desk, storage, again, attempt=attempt)
    assert outcome.grading == "in_progress" and again.calls == []
    assert len(requested(desk)) == 1


def _grade_at(desk: Desk, storage: FakeStorage, attempt: uuid.UUID, stub: Stub, now: datetime):  # noqa: ANN202
    from core_api.grading import grade_attempt

    return grade_attempt(
        desk.session, desk.user, attempt, stub, environment="production", storage=storage, now=now
    )


def test_a_queued_grading_older_than_the_limit_is_asked_again(
    desk: Desk, storage: FakeStorage
) -> None:
    attempt, _ = queue(desk, storage)
    later = NOW + timedelta(hours=1, seconds=1)
    outcome = _grade_at(desk, storage, attempt, Stub(failure=UNAVAILABLE), later)
    assert outcome.grading == "in_progress"
    events = requested(desk)
    assert len(events) == 2
    assert events[0].payload["request_key"] != events[1].payload["request_key"]
    job = GradeJobRepository(desk.session, desk.user.id).for_attempt(attempt)
    assert job is not None and job.updated_at == later


def test_a_queued_grading_within_the_limit_stays_in_progress(
    desk: Desk, storage: FakeStorage
) -> None:
    attempt, _ = queue(desk, storage)
    again = Stub()
    outcome = _grade_at(desk, storage, attempt, again, NOW + timedelta(minutes=59))
    assert outcome.grading == "in_progress" and again.calls == []
    assert len(requested(desk)) == 1


def test_the_view_of_an_overdue_queued_grading_offers_regrade(
    desk: Desk, storage: FakeStorage
) -> None:
    from core_api.repositories.review import AttemptRepository

    attempt, _ = queue(desk, storage)
    found = AttemptRepository(desk.session, desk.user.id).get(attempt)
    assert found is not None
    fresh = attempt_view(desk.session, desk.user.id, found, None, now=NOW + timedelta(minutes=5))
    assert fresh.grading == "in_progress"
    late = attempt_view(desk.session, desk.user.id, found, None, now=NOW + timedelta(hours=2))
    assert (late.grading, late.failure) == ("failed", "unavailable")


def test_another_user_cannot_ask_an_overdue_grading_again(
    desk: Desk, storage: FakeStorage, two_users: tuple[User, User]
) -> None:
    from core_api.grading import grade_attempt
    from core_api.repositories.review import AttemptNotFoundError

    attempt, _ = queue(desk, storage)
    with pytest.raises(AttemptNotFoundError):
        grade_attempt(
            desk.session,
            two_users[1],
            attempt,
            Stub(),
            environment="production",
            storage=storage,
            now=NOW + timedelta(hours=5),
        )
    assert len(requested(desk)) == 1


def test_without_a_storage_the_failure_is_as_before(desk: Desk) -> None:
    _, outcome = queue(desk, None)
    assert (outcome.grading, outcome.failure) == ("failed", "unavailable")
    assert requested(desk) == []


@pytest.mark.parametrize(
    "failure", [NotGraded("invalid", "grade_invalid"), NotGraded("disabled", "grading_disabled")]
)
def test_a_failure_that_cannot_clear_is_not_queued(
    desk: Desk, storage: FakeStorage, failure: NotGraded
) -> None:
    _, outcome = queue(desk, storage, Stub(failure=failure))
    assert (outcome.grading, outcome.failure) == ("failed", failure.failure)
    assert requested(desk) == [] and storage.objects == {}


def test_the_storage_being_down_leaves_the_old_failure_and_nothing_queued(
    desk: Desk, storage: FakeStorage
) -> None:
    storage.down = True
    attempt, outcome = queue(desk, storage)
    assert (outcome.grading, outcome.failure) == ("failed", "unavailable")
    assert requested(desk) == []
    assert GradeJobRepository(desk.session, desk.user.id).for_attempt(attempt) is None


def test_the_dont_remember_answer_never_queues(desk: Desk, storage: FakeStorage) -> None:
    attempt = desk.submitted("", forgot=True)
    _, outcome = queue(desk, storage, attempt=attempt)
    assert outcome.grading == "graded" and requested(desk) == []


# --- The way out: grade.completed.v1 -------------------------------------------------------------


def test_the_result_is_recorded_like_a_synchronous_grade(desk: Desk, storage: FakeStorage) -> None:
    attempt, request_key = queued(desk, storage)
    key = answered(desk, storage, request_key)
    handler(storage)(desk.session, completed_event(desk.user, attempt, key))

    grade = desk.session.scalars(select(Grade)).one()
    assert (grade.source, grade.overall, grade.attempt_id) == ("ai", "correct", attempt)
    assert (desk.count(Grade), desk.count(GradeUnit), desk.count(ReviewLog)) == (1, 2, 2)
    assert GradeJobRepository(desk.session, desk.user.id).for_attempt(attempt) is None
    assert storage.objects == {}  # the request holds the answer: it goes with the job
    shown = view(desk, attempt)
    assert shown.grading == "graded" and shown.result is not None


def test_the_same_event_twice_writes_one_grade(desk: Desk, storage: FakeStorage) -> None:
    attempt, request_key = queued(desk, storage)
    event = completed_event(desk.user, attempt, answered(desk, storage, request_key))
    handler(storage)(desk.session, event)
    handler(storage)(desk.session, event)
    assert (desk.count(Grade), desk.count(ReviewLog)) == (1, 2)


def test_a_grade_written_meanwhile_wins(desk: Desk, storage: FakeStorage) -> None:
    """The user pressed "Chấm lại" after ai-service came back: the late result adds nothing."""
    attempt, request_key = queued(desk, storage)
    key = answered(desk, storage, request_key)
    GradeJobRepository(desk.session, desk.user.id).done(attempt)
    queue(desk, storage, Stub(), attempt=attempt)
    assert desk.count(Grade) == 1
    handler(storage)(desk.session, completed_event(desk.user, attempt, key))
    assert (desk.count(Grade), desk.count(ReviewLog)) == (1, 2)


def test_a_failed_result_marks_the_job_and_offers_regrade(desk: Desk, storage: FakeStorage) -> None:
    attempt, request_key = queued(desk, storage)
    key = request_key.replace("/request-", "/result-")
    storage.write(key, b'{"status":"failed","failure":"invalid"}', content_type="x")
    handler(storage)(desk.session, completed_event(desk.user, attempt, key))

    assert desk.count(Grade) == 0
    shown = view(desk, attempt)
    assert (shown.grading, shown.failure) == ("failed", "invalid")
    # "Chấm lại" asks again, and may queue again.
    _, outcome = queue(desk, storage, attempt=attempt)
    assert outcome.grading == "in_progress"


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("missing", None),
        ("not json", b"nope"),
        ("extra field", b'{"status":"failed","failure":"invalid","answer":"x"}'),
        ("unknown failure", b'{"status":"failed","failure":"unavailable"}'),
    ],
)
def test_a_result_that_breaks_the_contract_is_failed_not_written(
    desk: Desk, storage: FakeStorage, name: str, body: bytes | None
) -> None:
    attempt, request_key = queued(desk, storage)
    key = request_key.replace("/request-", "/result-")
    if body is not None:
        storage.write(key, body, content_type="x")
    handler(storage)(desk.session, completed_event(desk.user, attempt, key))
    assert desk.count(Grade) == 0
    assert (view(desk, attempt).grading, view(desk, attempt).failure) == ("failed", "invalid")


def test_an_answer_that_does_not_fit_the_units_is_refused(desk: Desk, storage: FakeStorage) -> None:
    attempt, request_key = queued(desk, storage)
    key = answered(desk, storage, request_key, units=[])  # R03 layer 2: the unit set differs
    handler(storage)(desk.session, completed_event(desk.user, attempt, key))
    assert desk.count(Grade) == 0 and view(desk, attempt).failure == "invalid"


def test_the_fake_grader_is_refused_in_production(desk: Desk, storage: FakeStorage) -> None:
    attempt, request_key = queued(desk, storage)
    key = answered(desk, storage, request_key, provider="fake")
    handler(storage, "production")(desk.session, completed_event(desk.user, attempt, key))
    assert desk.count(Grade) == 0 and view(desk, attempt).failure == "invalid"


def test_a_change_of_units_since_the_request_is_refused(desk: Desk, storage: FakeStorage) -> None:
    from sqlalchemy import delete

    from core_api.db.models import QuestionUnit

    attempt, request_key = queued(desk, storage)
    key = answered(desk, storage, request_key)
    desk.session.execute(
        delete(QuestionUnit).where(
            QuestionUnit.question_id == desk.question.id, QuestionUnit.unit_id == desk.units[1]
        )
    )
    handler(storage)(desk.session, completed_event(desk.user, attempt, key))
    assert desk.count(Grade) == 0 and view(desk, attempt).failure == "invalid"


def test_the_storage_being_down_fails_the_handler_to_be_retried(
    desk: Desk, storage: FakeStorage
) -> None:
    attempt, request_key = queued(desk, storage)
    key = answered(desk, storage, request_key)
    storage.down = True
    with pytest.raises(StorageUnavailableError):
        handler(storage)(desk.session, completed_event(desk.user, attempt, key))
    job = GradeJobRepository(desk.session, desk.user.id).for_attempt(attempt)
    assert desk.count(Grade) == 0 and job is not None and job.status == "queued"


def test_an_event_for_another_users_attempt_is_ignored(
    desk: Desk, two_users: tuple[User, User], storage: FakeStorage
) -> None:
    """F2: Bob's event names Alice's attempt: nothing is written, nothing of Alice's changes."""
    attempt, _ = queued(desk, storage)
    bob = two_users[1]
    own = f"users/{bob.id}/grading/{attempt}/result-x.json"
    storage.write(own, (b'{"status":"failed","failure":"invalid"}'), content_type="x")
    handler(storage)(desk.session, completed_event(bob, attempt, own))
    job = GradeJobRepository(desk.session, desk.user.id).for_attempt(attempt)
    assert desk.count(Grade) == 0 and job is not None and job.status == "queued"
    assert own in storage.objects  # not even read


def test_a_result_key_outside_the_attempts_directory_is_ignored(
    desk: Desk, storage: FakeStorage
) -> None:
    attempt, _ = queued(desk, storage)
    elsewhere = f"users/{desk.user.id}/grading/{uuid.uuid4()}/result-x.json"
    storage.write(elsewhere, b'{"status":"failed","failure":"invalid"}', content_type="x")
    handler(storage)(desk.session, completed_event(desk.user, attempt, elsewhere))
    job = GradeJobRepository(desk.session, desk.user.id).for_attempt(attempt)
    assert job is not None and job.status == "queued"


def test_an_attempt_graded_by_a_request_in_flight_is_retried(
    desk: Desk, storage: FakeStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core_api.repositories.review import GradeRepository

    attempt, request_key = queued(desk, storage)
    key = answered(desk, storage, request_key)

    def held(self: GradeRepository, attempt_id: uuid.UUID) -> bool:
        return False

    monkeypatch.setattr(GradeRepository, "try_lock_attempt", held)
    with pytest.raises(GradingBusyError):
        handler(storage)(desk.session, completed_event(desk.user, attempt, key))


def test_the_logs_hold_no_answer(
    desk: Desk, storage: FakeStorage, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("DEBUG"):
        attempt, request_key = queued(desk, storage)
        key = request_key.replace("/request-", "/result-")
        storage.write(key, "Câu trả lời của tôi".encode(), content_type="x")
        handler(storage)(desk.session, completed_event(desk.user, attempt, key))
    assert "Câu trả lời của tôi" not in caplog.text


def test_the_consumer_handles_grade_completed_besides_the_document_events() -> None:
    from core_api.messaging.consumer import build_handlers

    handlers = build_handlers()
    assert isinstance(handlers["grade.completed.v1"], OnGradeCompleted)
    assert {"document.indexed.v1", "document.failed.v1"} <= set(handlers)
