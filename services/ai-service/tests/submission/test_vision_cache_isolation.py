"""T7.7 / US-02 AC8, ADR-0012 (tester): the vision cache is per learner THROUGH THE HANDLER
(review Y-b, point 2).

The existing test only checks `StorageVisionCache` itself: if the handler built it with another
id (the subject, the session) or the class lost the user in its prefix, two learners submitting
the same image would share a reading. Two events, two users, the same subject and the same image
bytes: each user's image is read by its own vision call and lands under its own prefix."""

import json
import uuid
from collections.abc import Iterator
from typing import Any, cast

import pytest
from redis import Redis
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from ai_service.db.models import LlmCall, PipelineRun
from ai_service.messaging.envelope import (
    SubmissionCreatedEvent,
    SubmissionProcessedEvent,
    parse_event,
)
from ai_service.tasks.process_submission import result_key_for
from tests.submission.helpers import SUBJECT, USER, Model, handler, png, run, submitted
from tests.tasks.helpers import FakeStorage

USER_B = uuid.UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
PNG = "image/png"


@pytest.fixture(autouse=True)
def clean_user_b(sessions: sessionmaker[Session]) -> Iterator[None]:
    for step in range(2):
        with sessions.begin() as s:
            s.execute(delete(LlmCall).where(LlmCall.user_id == USER_B))
            s.execute(delete(PipelineRun).where(PipelineRun.user_id == USER_B))
        if step == 0:
            yield


def submitted_by(storage: FakeStorage, user: uuid.UUID, image: bytes) -> SubmissionCreatedEvent:
    """A submission of `user`: one image, no mention; every key under the user's own prefix."""
    submission_id, session_id = uuid.uuid4(), uuid.uuid4()
    context_key = f"users/{user}/sessions/{session_id}/context/{submission_id}.json"
    storage.objects[context_key] = json.dumps(
        {"version": 1, "description": None, "mentions": [], "existing_units": []}
    ).encode()
    file_key = f"users/{user}/sessions/{session_id}/notes/{uuid.uuid4().hex}.png"
    storage.objects[file_key] = image
    event = parse_event(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "submission.created.v1",
                "schema_version": 1,
                "occurred_at": "2026-11-01T08:30:00.000000Z",
                "user_id": str(user),
                "trace_context": {},
                "payload": {
                    "submission_id": str(submission_id),
                    "study_session_id": str(session_id),
                    "subject_id": str(SUBJECT),
                    "file_keys": [{"object_key": file_key, "mime": PNG}],
                    "context_key": context_key,
                },
            }
        )
    )
    assert isinstance(event, SubmissionCreatedEvent)
    return event


def sent(redis: Redis, stream: str) -> list[Any]:
    return [parse_event(f["envelope"]) for _, f in cast(Any, redis.xrange(stream))]


def test_us02_ac8_two_users_same_image_each_read_by_their_own_vision_call(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: the handler keys the vision cache by anything but the event's user (subject,
    # session, a shared prefix): user B would get user A's reading with no call.
    storage = FakeStorage()
    model = Model()
    h = handler(storage, redis_client, stream, sessions, model)
    image = png(42)

    run(h, submitted_by(storage, USER, image))
    run(h, submitted_by(storage, USER_B, image))

    readers = [r.user_id for r in model.calls("read_notes")]
    assert readers == [USER, USER_B]
    vision_keys = [k for k in storage.objects if "/derived/vision/" in k]
    assert len(vision_keys) == 2
    assert {k.split("/")[1] for k in vision_keys} == {str(USER), str(USER_B)}
    assert all(k.startswith(f"users/{k.split('/')[1]}/derived/vision/") for k in vision_keys)
    assert all(isinstance(e, SubmissionProcessedEvent) for e in sent(redis_client, stream))


def test_us02_ac8_user_b_cached_reading_never_reaches_user_a(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: a reading cached for one user answers another's image (cross-user leak of notes
    # text). User B's cache holds a poisoned text for the very key A's image hashes to; A must
    # make its own call and its result must not carry B's text.
    from ai_service.tasks import read_notes_image

    storage = FakeStorage()
    image = png(43)
    poisoned = "TEXT OF USER B ONLY: ty the la noi hop ho hap."
    key = read_notes_image.cache_key(image)
    storage.objects[f"users/{USER_B}/derived/vision/{key}.json"] = json.dumps(
        {"text": poisoned}
    ).encode()
    model = Model()
    event = submitted_by(storage, USER, image)
    run(handler(storage, redis_client, stream, sessions, model), event)

    assert len(model.calls("read_notes")) == 1
    assert poisoned not in storage.objects[result_key_for(event)].decode()
    for request in model.calls("draft_units"):
        assert poisoned not in json.dumps(request.payload) + request.user


def test_us02_ac8_same_user_two_subjects_share_the_reading(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: the cache is keyed by subject (or session) instead of user: the same learner's
    # same image in another subject is read again (AC8 counts calls per image, per learner).
    storage = FakeStorage()
    model = Model()
    h = handler(storage, redis_client, stream, sessions, model)
    image = png(44)
    first = submitted(storage, files=[_file(storage, image)], mentions=[])
    run(h, first)
    other_subject = first.model_copy(
        update={
            "event_id": uuid.uuid4(),
            "payload": first.payload.model_copy(
                update={"subject_id": uuid.uuid4(), "submission_id": uuid.uuid4()}
            ),
        }
    )
    run(h, other_subject)
    assert len(model.calls("read_notes")) == 1


def _file(storage: FakeStorage, data: bytes) -> dict[str, str]:
    key = f"users/{USER}/sessions/{uuid.uuid4()}/notes/{uuid.uuid4().hex}.png"
    storage.objects[key] = data
    return {"object_key": key, "mime": PNG}
