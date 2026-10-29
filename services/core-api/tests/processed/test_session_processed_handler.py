"""T4.17 (US-02 AC13, Bảo mật): the handler of `session.processed.v1` writes the units, anchors,
questions and links of a confirmed session in one transaction, and trusts neither the event nor
the file. Storage is a double; the database is real."""

import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from result_builders import anchor, encode, question, result, unit
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.clients.storage import StorageUnavailableError
from core_api.db.models import (
    Anchor,
    Document,
    KnowledgeUnit,
    Question,
    QuestionUnit,
    StudySession,
    Subject,
    UnitLineage,
    User,
)
from core_api.handlers.session_processed import MAX_RESULT_BYTES, OnSessionProcessed
from core_api.messaging.envelope import Event, parse_event
from fake_storage import FakeStorage
from sessions.session_helpers import indexed_document, subject_of

U1, U2, U3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
RUN = uuid.uuid4()


class World:
    """A user with a subject, an indexed document and a confirmed session."""

    def __init__(self, db: Session, user: User, storage: FakeStorage) -> None:
        self.db, self.user, self.storage = db, user, storage
        self.subject: Subject = subject_of(db, user)
        self.document: Document = indexed_document(db, storage, user, self.subject)
        self.study = self.confirmed()

    def confirmed(self, status: str = "confirmed") -> StudySession:
        study = StudySession(
            user_id=self.user.id,
            subject_id=self.subject.id,
            description_raw="học chương 3",
            extraction="proposed",
            status=status,
        )
        if status == "confirmed":
            study.studied_on = study.learning_day = datetime(2026, 10, 29, tzinfo=UTC).date()
            study.confirmed_at = datetime(2026, 10, 29, tzinfo=UTC)
        self.db.add(study)
        self.db.flush()
        return study

    def key(self, study: StudySession | None = None, name: str | None = None) -> str:
        study = study or self.study
        name = name or f"result-{uuid.uuid4()}.json"
        return f"users/{self.user.id}/subjects/{study.subject_id}/sessions/{study.id}/{name}"

    def put(self, body: dict[str, Any] | bytes, key: str | None = None) -> str:
        key = key or self.key()
        data = body if isinstance(body, bytes) else encode(body)
        self.storage.write(key, data, content_type="application/json")
        return key

    def body(self, **over: Any) -> dict[str, Any]:
        return result(self.study.id, **over)

    def unit(self, unit_id: uuid.UUID, **over: Any) -> dict[str, Any]:
        return unit(unit_id, self.document.id, **over)

    def event(
        self, key: str, *, user: User | None = None, study: StudySession | None = None
    ) -> Event:
        return parse_event(
            json.dumps(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "session.processed.v1",
                    "schema_version": 1,
                    "occurred_at": "2026-10-29T08:01:00.000000Z",
                    "user_id": str((user or self.user).id),
                    "trace_context": {},
                    "payload": {
                        "study_session_id": str((study or self.study).id),
                        "run_id": str(RUN),
                        "result_key": key,
                    },
                }
            )
        )

    def run(self, body: dict[str, Any] | bytes, **kw: Any) -> str:
        key = self.put(body)
        OnSessionProcessed(self.storage)(self.db, self.event(key, **kw))
        return key


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def world(db_session: Session, two_users: tuple[User, User], storage: FakeStorage) -> World:
    return World(db_session, two_users[0], storage)


def count(db: Session, model: type, user: User | None = None) -> int:
    query = select(func.count()).select_from(model)
    if user is not None:
        query = query.where(model.user_id == user.id)  # type: ignore[attr-defined]
    return db.scalar(query) or 0


def full(world: World) -> dict[str, Any]:
    return world.body(
        units=[world.unit(U1), world.unit(U2)],
        questions=[
            question([U1], 1, prompt="Câu 1"),
            question([U2], 2, prompt="Câu 2"),
            question([U1, U2], 3, prompt="Câu 3"),
        ],
    )


def test_processed_writes_units_anchors_questions_links(world: World) -> None:
    world.run(full(world))
    db = world.db
    assert count(db, KnowledgeUnit, world.user) == 2
    assert count(db, Anchor, world.user) == 2
    assert count(db, Question, world.user) == 3
    assert count(db, QuestionUnit, world.user) == 4
    unit_row = db.scalars(select(KnowledgeUnit)).first()
    assert unit_row is not None
    assert unit_row.subject_id == world.subject.id
    assert unit_row.run_id == RUN
    assert unit_row.section_id is None
    assert unit_row.id not in {U1, U2}  # ids are the server's own
    anchor_row = db.scalars(select(Anchor)).first()
    assert anchor_row is not None
    assert (anchor_row.document_id, anchor_row.page_no) == (world.document.id, 3)
    assert (anchor_row.char_start, anchor_row.char_end) == (0, 12)
    level3 = db.scalars(select(Question).where(Question.level == 3)).one()
    assert count(db, QuestionUnit) == 4
    linked = db.scalars(select(QuestionUnit.unit_id).where(QuestionUnit.question_id == level3.id))
    assert len(set(linked)) == 2
    assert level3.rubric == "Nêu đúng ý chính."


def test_lineage_rows_only_for_own_units(world: World, db_session: Session) -> None:
    older = KnowledgeUnit(
        user_id=world.user.id,
        subject_id=world.subject.id,
        title="Cũ",
        summary="s",
        kind="concept",
        run_id=RUN,
    )
    db_session.add(older)
    other_subject = subject_of(db_session, world.user)
    elsewhere = KnowledgeUnit(
        user_id=world.user.id,
        subject_id=other_subject.id,
        title="Môn khác",
        summary="s",
        kind="concept",
        run_id=RUN,
    )
    db_session.add(elsewhere)
    db_session.flush()
    world.run(
        world.body(
            units=[
                world.unit(U1, lineage=[str(older.id), str(elsewhere.id), str(uuid.uuid4())]),
            ]
        )
    )
    rows = db_session.scalars(select(UnitLineage)).all()
    assert [r.old_unit_id for r in rows] == [older.id]
    assert db_session.get(KnowledgeUnit, older.id).status == "active"  # type: ignore[union-attr]


def test_redelivered_event_adds_no_duplicate_questions(world: World) -> None:
    key = world.put(full(world))
    event = world.event(key)
    handler = OnSessionProcessed(world.storage)
    handler(world.db, event)
    handler(world.db, event)  # the consumer's claim stops a real redelivery; the data holds anyway
    assert count(world.db, Question) == 3


def test_same_prompt_in_new_event_adds_no_second_active_question(world: World) -> None:
    world.run(full(world))
    older_links = set(world.db.execute(select(QuestionUnit.question_id, QuestionUnit.unit_id)))
    second = world.body(units=[world.unit(U3)], questions=[question([U3], 1, prompt="Câu 1")])
    world.run(second)
    assert count(world.db, Question) == 3
    assert older_links <= set(
        world.db.execute(select(QuestionUnit.question_id, QuestionUnit.unit_id))
    )  # the old question keeps its units: no new link (us-04b AC1)
    assert count(world.db, QuestionUnit) == 4


def test_two_users_results_do_not_mix(
    db_session: Session, two_users: tuple[User, User], storage: FakeStorage
) -> None:
    alice, bob = two_users
    a, b = World(db_session, alice, storage), World(db_session, bob, storage)
    a.run(a.body(units=[a.unit(U1)], questions=[question([U1], prompt="A hỏi")]))
    b.run(b.body(units=[b.unit(U1)], questions=[question([U1], prompt="B hỏi")]))
    for owner, prompt in ((alice, "A hỏi"), (bob, "B hỏi")):
        rows = db_session.scalars(select(Question).where(Question.user_id == owner.id)).all()
        assert [q.prompt for q in rows] == [prompt]
        assert count(db_session, KnowledgeUnit, owner) == 1
    mixed = (
        select(func.count())
        .select_from(KnowledgeUnit)
        .where(KnowledgeUnit.user_id == alice.id, KnowledgeUnit.subject_id == b.subject.id)
    )
    assert db_session.scalar(mixed) == 0


def test_event_user_id_not_session_owner_is_refused(
    db_session: Session, two_users: tuple[User, User], storage: FakeStorage
) -> None:
    alice, bob = two_users
    a = World(db_session, alice, storage)
    b = World(db_session, bob, storage)
    # Bob's event names Alice's session, with a key under Bob's own prefix.
    key = f"users/{bob.id}/subjects/{a.subject.id}/sessions/{a.study.id}/result-{uuid.uuid4()}.json"
    b.put(a.body(units=[a.unit(U1)]), key)
    OnSessionProcessed(storage)(db_session, b.event(key, study=a.study))
    assert count(db_session, KnowledgeUnit) == 0


def test_draft_or_missing_session_ignored(world: World) -> None:
    draft = world.confirmed("draft")
    key = world.put(world.body(units=[world.unit(U1)]), world.key(draft))
    OnSessionProcessed(world.storage)(world.db, world.event(key, study=draft))
    missing = world.event(world.key(), study=draft)
    OnSessionProcessed(world.storage)(world.db, missing)
    assert count(world.db, KnowledgeUnit) == 0


KeyMaker = Callable[[World], str]
Mutation = Callable[[World, dict[str, Any]], object]
KEYS: list[KeyMaker] = [
    lambda w: (
        f"users/{w.user.id}/subjects/{w.subject.id}/sessions/{uuid.uuid4()}/result-{uuid.uuid4()}.json"
    ),
    lambda w: (
        f"users/{w.user.id}/subjects/{uuid.uuid4()}/sessions/{w.study.id}/result-{uuid.uuid4()}.json"
    ),
    lambda w: w.key(name="result-abc.json"),
    lambda w: w.key(name="result-" + str(uuid.uuid4()) + ".json.bak"),
    lambda w: f"users/{w.user.id}/subjects/{w.subject.id}/derived/x/result.json",
]


@pytest.mark.parametrize("make_key", KEYS)
def test_result_key_not_the_derived_key_is_refused(world: World, make_key: KeyMaker) -> None:
    key = make_key(world)
    world.put(world.body(units=[world.unit(U1)]), key)
    reads: list[str] = []
    real = world.storage.read
    world.storage.read = lambda k, *, max_bytes: reads.append(k) or real(k, max_bytes=max_bytes)  # type: ignore[method-assign]
    OnSessionProcessed(world.storage)(world.db, world.event(key))
    assert reads == []
    assert count(world.db, KnowledgeUnit) == 0


def test_key_valid_after_outbox_cleanup(world: World) -> None:
    # No outbox row is read at all: the key comes from the locked session.
    world.run(world.body(units=[world.unit(U1)]))
    assert count(world.db, KnowledgeUnit) == 1


def test_oversized_result_is_not_read_into_memory(world: World) -> None:
    world.put(b"x" * (MAX_RESULT_BYTES + 1), key := world.key())
    with pytest.raises(StorageUnavailableError):
        OnSessionProcessed(world.storage)(world.db, world.event(key))
    assert count(world.db, KnowledgeUnit) == 0


def test_valid_result_over_2mib_is_written(world: World) -> None:
    big = "Giải thích " * 200
    units = [world.unit(uuid.uuid4(), summary=big) for _ in range(1200)]
    raw = encode(world.body(units=units))
    assert 2 * 1024 * 1024 < len(raw) < MAX_RESULT_BYTES
    world.run(raw)
    assert count(world.db, KnowledgeUnit) == 1200


def test_missing_result_writes_nothing(world: World) -> None:
    OnSessionProcessed(world.storage)(world.db, world.event(world.key()))
    assert count(world.db, KnowledgeUnit) == 0


def test_storage_down_raises_so_the_consumer_retries(world: World) -> None:
    key = world.put(world.body(units=[world.unit(U1)]))
    world.storage.down = True
    with pytest.raises(StorageUnavailableError):
        OnSessionProcessed(world.storage)(world.db, world.event(key))


MUTATIONS: list[Mutation] = [
    lambda w, b: b.pop("skipped"),
    lambda w, b: b.update(extra=1),
    lambda w, b: b["questions"].append(question([U1], level=4)),
    lambda w, b: b.update(study_session_id=str(uuid.uuid4())),
    lambda w, b: b["units"].append(w.unit(U1)),  # same unit id twice
]


@pytest.mark.parametrize("mutate", MUTATIONS)
def test_result_breaking_the_schema_writes_nothing(world: World, mutate: Mutation) -> None:
    body = world.body(units=[world.unit(U1)], questions=[question([U1], prompt="Có")])
    mutate(world, body)
    world.run(body)
    assert (count(world.db, KnowledgeUnit), count(world.db, Question)) == (0, 0)


def test_not_json_writes_nothing(world: World) -> None:
    world.run(b"{not json")
    assert count(world.db, KnowledgeUnit) == 0


def test_bad_items_are_dropped_and_the_rest_written(world: World) -> None:
    world.run(
        world.body(
            units=[
                world.unit(U1, anchors=[anchor(uuid.uuid4())]),  # a document of nobody here
                world.unit(U2),
            ],
            questions=[
                question([U1], prompt="Trên mảnh bị bỏ"),
                question([U2], 1, prompt="Giữ"),
                question([U2], 3, prompt="L3 một mảnh"),
            ],
        )
    )
    assert [u.title for u in world.db.scalars(select(KnowledgeUnit))] == [f"Mảnh {str(U2)[:4]}"]
    assert [q.prompt for q in world.db.scalars(select(Question))] == ["Giữ"]


def test_document_anchor_of_foreign_document_dropped(
    db_session: Session, two_users: tuple[User, User], storage: FakeStorage
) -> None:
    alice, bob = two_users
    a, b = World(db_session, alice, storage), World(db_session, bob, storage)
    a.run(a.body(units=[a.unit(U1, anchors=[anchor(b.document.id)])]))
    assert count(db_session, Anchor) == 0
    assert count(db_session, KnowledgeUnit) == 0


def test_document_of_another_subject_is_not_this_sessions(world: World) -> None:
    other = subject_of(world.db, world.user)
    elsewhere = indexed_document(world.db, world.storage, world.user, other, sha="ef" * 32)
    world.run(world.body(units=[unit(U1, elsewhere.id)]))
    assert count(world.db, KnowledgeUnit) == 0


def test_merge_of_foreign_or_other_subject_unit_is_skipped(
    db_session: Session, two_users: tuple[User, User], storage: FakeStorage
) -> None:
    alice, bob = two_users
    a, b = World(db_session, alice, storage), World(db_session, bob, storage)
    theirs = KnowledgeUnit(
        user_id=bob.id,
        subject_id=b.subject.id,
        title="Của B",
        summary="s",
        kind="concept",
        run_id=RUN,
    )
    mine = KnowledgeUnit(
        user_id=alice.id,
        subject_id=a.subject.id,
        title="Của A",
        summary="s",
        kind="concept",
        run_id=RUN,
    )
    elsewhere_subject = subject_of(db_session, alice)
    elsewhere = KnowledgeUnit(
        user_id=alice.id,
        subject_id=elsewhere_subject.id,
        title="Môn khác",
        summary="s",
        kind="concept",
        run_id=RUN,
    )
    db_session.add_all([theirs, mine, elsewhere])
    db_session.flush()
    merges = [
        {"existing_unit_id": str(theirs.id), "anchors": [anchor(a.document.id)]},
        {"existing_unit_id": str(elsewhere.id), "anchors": [anchor(a.document.id)]},
        {"existing_unit_id": str(mine.id), "anchors": [anchor(a.document.id)]},
    ]
    a.run(a.body(merges=merges))
    owners = {r.unit_id for r in db_session.scalars(select(Anchor))}
    assert owners == {mine.id}


def test_failure_midway_rolls_back_everything(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core_api.repositories import question as question_repo

    calls = {"n": 0}
    real = question_repo.QuestionUnitRepository.link_once

    def boom(self: Any, question_id: uuid.UUID, unit_id: uuid.UUID) -> bool:
        calls["n"] += 1
        if calls["n"] == 4:
            raise RuntimeError("boom")
        return real(self, question_id, unit_id)

    monkeypatch.setattr(question_repo.QuestionUnitRepository, "link_once", boom)
    key = world.put(full(world))
    handler = OnSessionProcessed(world.storage)
    with pytest.raises(RuntimeError):
        with world.db.begin_nested():
            handler(world.db, world.event(key))
    assert (count(world.db, KnowledgeUnit), count(world.db, Question)) == (0, 0)


def test_handler_logs_hold_no_text(world: World, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    body = full(world)
    key = world.put(body)
    OnSessionProcessed(world.storage)(world.db, world.event(key))
    world.put(b"{not json" + "Bí mật".encode(), key)
    OnSessionProcessed(world.storage)(world.db, world.event(key))
    text = "\n".join(
        record.getMessage() + json.dumps(record.__dict__, default=str) for record in caplog.records
    )
    for secret in ("Câu 1", "Mảnh", "Một câu trích", "Bí mật", "result-"):
        assert secret not in text


def test_nul_removed_all_text_fields(world: World) -> None:
    world.run(
        world.body(
            units=[
                world.unit(
                    U1,
                    title="Ti\x00êu",
                    summary="Tóm\x00",
                    anchors=[anchor(world.document.id, quote_text="Trích\x00")],
                )
            ],
            questions=[
                question(
                    [U1],
                    prompt="Hỏi\x00",
                    reference_answer="Đáp\x00",
                    rubric="Rubric\x00",
                )
            ],
        )
    )
    q = world.db.scalars(select(Question)).one()
    assert (q.prompt, q.reference_answer, q.rubric) == ("Hỏi", "Đáp", "Rubric")


def test_question_on_dropped_unit_dropped_rest_written(world: World) -> None:
    world.run(
        world.body(
            units=[world.unit(U1, title="\x00"), world.unit(U2)],
            questions=[question([U1], prompt="Mồ côi"), question([U2], prompt="Còn")],
        )
    )
    assert [q.prompt for q in world.db.scalars(select(Question))] == ["Còn"]


def test_subject_gone_after_confirm_is_ignored(world: World) -> None:
    from sqlalchemy import text

    key = world.put(world.body(units=[world.unit(U1)]))
    event = world.event(key)
    world.db.execute(
        text("UPDATE subject SET deleted_at = now() WHERE id = :i"), {"i": world.subject.id}
    )
    OnSessionProcessed(world.storage)(world.db, event)
    assert count(world.db, KnowledgeUnit) == 0


def test_merge_into_inactive_unit_is_skipped(world: World) -> None:
    old = KnowledgeUnit(
        user_id=world.user.id,
        subject_id=world.subject.id,
        title="Đã gộp",
        summary="s",
        kind="concept",
        status="merged",
        run_id=RUN,
    )
    world.db.add(old)
    world.db.flush()
    world.run(
        world.body(
            merges=[{"existing_unit_id": str(old.id), "anchors": [anchor(world.document.id)]}]
        )
    )
    assert count(world.db, Anchor) == 0
