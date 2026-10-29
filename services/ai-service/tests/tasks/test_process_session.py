"""The `session.confirmed.v1` handler (T4.16b, US-02 AC7/8/12/13, US-02b, US-04b): page text and
notes in, units and questions in a result file, `session.processed.v1` out. Fake model on the
real test database; storage and Redis as in T4.7 and T4.19."""

import json
import logging
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from redis import Redis
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.clients.storage import StorageUnavailable
from ai_service.db.models import LlmCall, PipelineRun
from ai_service.llm.client import AuditUnavailableError, LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import ProviderError
from ai_service.messaging.consumer import Deferred
from ai_service.messaging.envelope import (
    SessionConfirmedEvent,
    SessionFailedEvent,
    SessionProcessedEvent,
    SessionProgressEvent,
    parse_event,
)
from ai_service.tasks.process_session import (
    ProcessSession,
    fake_chunk,
    fake_questions,
    result_key_for,
)
from tests.llm.helpers import NoQuota
from tests.tasks.helpers import FakeStorage

_SCHEMA_FILE = (
    Path(__file__).resolve().parents[4] / "contracts" / "files" / "session-result.v1.schema.json"
)
SCHEMA: Any = Draft202012Validator(json.loads(_SCHEMA_FILE.read_text(encoding="utf-8")))
USER = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SUBJECT = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
DOC = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
PAGE_TEXTS = {
    1: "Mitochondria are the site of cellular respiration in eukaryotic cells.",
    2: "The Krebs cycle oxidises acetyl-CoA to carbon dioxide in the matrix.",
    3: "Ribosomes translate messenger RNA into protein chains.",
}
NOTE = "ghi chu: ty the la noi hop ho hap te bao."
SECRET = "SECRET-NOTE-TEXT-9921"


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_audit(sessions: sessionmaker[Session]) -> Iterator[None]:
    # Before and after: rows with the new tasks would stop the migration down-and-up test.
    for _ in range(2):
        with sessions.begin() as s:
            s.execute(delete(LlmCall).where(LlmCall.user_id == USER))
            s.execute(delete(PipelineRun).where(PipelineRun.user_id == USER))
        if _ == 0:
            yield


@pytest.fixture
def stream(redis_client: Redis) -> Iterator[str]:
    name = f"test.events.ai.{uuid.uuid4()}"
    yield name
    redis_client.delete(name)


def prefix() -> str:
    return f"users/{USER}/subjects/{SUBJECT}"


def index(storage: FakeStorage, pages: dict[int, str] | None = None) -> None:
    pages = PAGE_TEXTS if pages is None else pages
    text_key = f"{prefix()}/documents/{DOC}/derived/run1/page_text.json"
    storage.objects[text_key] = json.dumps(
        {"pages": [{"page": n, "text": t, "needs_vision": False} for n, t in pages.items()]}
    ).encode()
    storage.objects[f"{prefix()}/documents/{DOC}/index.json"] = json.dumps(
        {"page_text_key": text_key, "page_count": len(pages)}
    ).encode()


def confirmed(
    ranges: list[tuple[uuid.UUID, int, int]] | None = None,
    notes: list[dict[str, str]] | None = None,
    existing: list[dict[str, Any]] | None = None,
) -> SessionConfirmedEvent:
    ranges = [(DOC, 1, 2)] if ranges is None else ranges
    event = parse_event(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "session.confirmed.v1",
                "schema_version": 1,
                "occurred_at": "2026-10-29T08:30:00.000000Z",
                "user_id": str(USER),
                "trace_context": {},
                "payload": {
                    "study_session_id": str(uuid.uuid4()),
                    "subject_id": str(SUBJECT),
                    "ranges": [
                        {"document_id": str(d), "first": a, "last": b, "depth": "deep"}
                        for d, a, b in ranges
                    ],
                    "notes": notes or [],
                    "existing_units": existing or [],
                },
            }
        )
    )
    assert isinstance(event, SessionConfirmedEvent)
    return event


def note(storage: FakeStorage, text: str = NOTE, mime: str = "text/plain") -> dict[str, str]:
    key = f"{prefix()}/notes/{uuid.uuid4()}.txt"
    storage.objects[key] = text.encode()
    return {"object_key": key, "mime": mime}


class Down:
    """A model that never answers."""

    provider = "anthropic"
    fixed_model: str | None = None
    params: dict[str, Any] = {}

    def complete(self, request: object, *, model: str, timeout: float) -> object:
        raise ProviderError("timeout")


def broken_chunker() -> FakeAdapter:
    return FakeAdapter({"chunk_units": lambda r: "not json", "generate_questions": fake_questions})


def handler(
    storage: FakeStorage,
    redis: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    adapter: Any = None,
    *,
    disabled: bool = False,
) -> ProcessSession:
    llm = (
        None
        if disabled
        else LlmClient(
            adapter
            or FakeAdapter({"chunk_units": fake_chunk, "generate_questions": fake_questions}),
            sessions,
            models={"chunk_units": "claude-haiku-5-5", "generate_questions": "claude-haiku-5-5"},
            quota_guard=NoQuota(),
        )
    )
    return ProcessSession(storage=storage, redis=redis, llm=llm, sessions=sessions, stream=stream)


def sent(redis: Redis, stream: str) -> list[Any]:
    return [parse_event(f["envelope"]) for _, f in cast(Any, redis.xrange(stream))]


def result(storage: FakeStorage, event: SessionConfirmedEvent) -> dict[str, Any]:
    body = json.loads(storage.objects[result_key_for(event)])
    assert list(SCHEMA.iter_errors(body)) == []
    return body


def run(h: ProcessSession, event: SessionConfirmedEvent) -> None:
    h(cast(Session, None), event)


def test_t416b_chain_writes_units_questions_and_announces(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed(notes=[note(storage)])
    run(handler(storage, redis_client, stream, sessions), event)

    body = result(storage, event)
    assert body["study_session_id"] == str(event.payload.study_session_id)
    # one unit per source: two pages and the notes
    assert len(body["units"]) == 3
    assert {a["page_no"] for u in body["units"] for a in u["anchors"]} == {1, 2, None}
    assert {q["unit_ids"][0] for q in body["questions"]} == {u["unit_id"] for u in body["units"]}
    out = sent(redis_client, stream)
    progress = [e.payload for e in out if isinstance(e, SessionProgressEvent)]
    assert progress[0].step == "reading_notes"
    assert "splitting_units" in {p.step for p in progress}
    assert progress[-1].step == "writing_questions"
    percents = [p.percent for p in progress]
    assert percents == sorted(percents)
    last = out[-1]
    assert isinstance(last, SessionProcessedEvent)
    assert last.payload.result_key == result_key_for(event)
    assert last.payload.study_session_id == event.payload.study_session_id


def test_t416b_anchors_are_cut_from_the_page_text(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    run(handler(storage, redis_client, stream, sessions), event)
    for unit in result(storage, event)["units"]:
        for a in unit["anchors"]:
            assert PAGE_TEXTS[a["page_no"]][a["start"] : a["end"]] == a["quote_text"]


def test_t416b_only_the_pages_of_the_range_are_read(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed(ranges=[(DOC, 2, 3)])
    run(handler(storage, redis_client, stream, sessions), event)
    pages = {a["page_no"] for u in result(storage, event)["units"] for a in u["anchors"]}
    assert pages == {2, 3}


def test_t416b_same_event_twice_pays_once_and_announces_the_same_event(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    h = handler(storage, redis_client, stream, sessions)
    run(h, event)
    with sessions() as s:
        calls = len(s.scalars(select(LlmCall).where(LlmCall.user_id == USER)).all())
    first = storage.objects[result_key_for(event)]
    run(h, event)
    assert storage.objects[result_key_for(event)] == first
    with sessions() as s:
        assert len(s.scalars(select(LlmCall).where(LlmCall.user_id == USER)).all()) == calls
    processed = [e for e in sent(redis_client, stream) if isinstance(e, SessionProcessedEvent)]
    assert len(processed) == 2
    assert processed[0].event_id == processed[1].event_id


def test_t416b_inverted_range_is_failed_before_anything_is_read(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    run(handler(storage, redis_client, stream, sessions), confirmed(ranges=[(DOC, 3, 1)]))
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SessionFailedEvent)
    assert out.payload.reason == "internal_error"
    assert storage.puts == []


def test_t416b_image_and_pdf_notes_are_skipped_with_a_reason(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    notes = [note(storage, mime="image/png"), note(storage, mime="application/pdf")]
    event = confirmed(notes=notes)
    run(handler(storage, redis_client, stream, sessions), event)
    skipped = result(storage, event)["skipped"]
    assert [s for s in skipped if s["kind"] == "note"] == [
        {"kind": "note", "ref": 1, "reason": "needs_ocr"},
        {"kind": "note", "ref": 2, "reason": "needs_ocr"},
    ]
    assert isinstance(sent(redis_client, stream)[-1], SessionProcessedEvent)


def test_t416b_notes_only_session_works(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = confirmed(ranges=[], notes=[note(storage)])
    run(handler(storage, redis_client, stream, sessions), event)
    body = result(storage, event)
    assert [a["source"] for u in body["units"] for a in u["anchors"]] == ["notes"]


def test_t416b_nothing_readable_is_unreadable(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()  # no index for the document, only an image note
    event = confirmed(notes=[note(storage, mime="image/jpeg")])
    run(handler(storage, redis_client, stream, sessions), event)
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SessionFailedEvent)
    assert out.payload.reason == "unreadable"
    assert result_key_for(event) not in storage.objects


def test_t416b_pointer_to_a_key_of_another_user_is_not_followed(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    other = f"users/{uuid.uuid4()}/subjects/{SUBJECT}/documents/{DOC}/derived/r/page_text.json"
    storage.objects[other] = json.dumps({"pages": [{"page": 1, "text": SECRET}]}).encode()
    storage.objects[f"{prefix()}/documents/{DOC}/index.json"] = json.dumps(
        {"page_text_key": other, "page_count": 1}
    ).encode()
    event = confirmed(ranges=[(DOC, 1, 1)])
    run(handler(storage, redis_client, stream, sessions), event)
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SessionFailedEvent) and out.payload.reason == "unreadable"


def test_t416b_model_down_is_failed_llm_unavailable(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    run(handler(storage, redis_client, stream, sessions, Down()), confirmed())
    out = sent(redis_client, stream)
    assert isinstance(out[-1], SessionFailedEvent)
    assert out[-1].payload.reason == "llm_unavailable"
    assert not any(isinstance(e, SessionProcessedEvent) for e in out)
    assert storage.puts == []


def test_t416b_disabled_model_is_failed_llm_unavailable(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    run(handler(storage, redis_client, stream, sessions, disabled=True), confirmed())
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SessionFailedEvent) and out.payload.reason == "llm_unavailable"


def test_t416b_model_that_always_breaks_the_rules_is_failed_internal_error(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    run(handler(storage, redis_client, stream, sessions, broken_chunker()), confirmed())
    out = sent(redis_client, stream)
    assert isinstance(out[-1], SessionFailedEvent)
    assert out[-1].payload.reason == "internal_error"
    with sessions() as s:
        runs = s.scalars(select(PipelineRun).where(PipelineRun.user_id == USER)).all()
    assert [r.status for r in runs if r.task == "chunk_units"] == ["failed"]


def test_t416b_a_crash_inside_the_model_call_is_failed_not_raised(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    def boom(request: object) -> str:
        raise RuntimeError(SECRET)

    storage = FakeStorage()
    index(storage)
    adapter = FakeAdapter({"chunk_units": boom, "generate_questions": fake_questions})  # pyright: ignore[reportArgumentType]
    run(handler(storage, redis_client, stream, sessions, adapter), confirmed())
    out = sent(redis_client, stream)
    assert isinstance(out[-1], SessionFailedEvent) and out[-1].payload.reason == "internal_error"


def test_t416b_storage_down_is_deferred(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    storage.get_error = StorageUnavailable()
    with pytest.raises(Deferred):
        run(handler(storage, redis_client, stream, sessions), confirmed())
    assert sent(redis_client, stream) == []


def test_t416b_storage_down_on_write_is_deferred(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    storage.put_error = StorageUnavailable()
    with pytest.raises(Deferred):
        run(handler(storage, redis_client, stream, sessions), confirmed())
    assert not any(isinstance(e, SessionProcessedEvent) for e in sent(redis_client, stream))


def test_t416b_many_pages_are_split_into_batches(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    pages = {n: f"Page number {n} says something distinct about topic {n}." for n in range(1, 46)}
    index(storage, pages)
    event = confirmed(ranges=[(DOC, 1, 45)])
    run(handler(storage, redis_client, stream, sessions), event)
    body = result(storage, event)
    assert len(body["units"]) == 45
    with sessions() as s:
        runs = s.scalars(select(PipelineRun).where(PipelineRun.user_id == USER)).all()
    assert {r.task for r in runs} == {"chunk_units", "generate_questions"}
    assert all(r.status == "succeeded" for r in runs)
    splitting = [
        e.payload.percent
        for e in sent(redis_client, stream)
        if isinstance(e, SessionProgressEvent) and e.payload.step == "splitting_units"
    ]
    assert len(splitting) == 3  # 45 pages, 20 a batch


def test_t416b_an_existing_unit_gets_anchors_and_no_question(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    existing_id = str(uuid.uuid4())
    # the title the fake model gives page 1: the code merges instead of creating
    event = confirmed(
        ranges=[(DOC, 1, 1)],
        existing=[{"unit_id": existing_id, "title": "Ý chính D1.p1", "summary": "x"}],
    )
    run(handler(storage, redis_client, stream, sessions), event)
    body = result(storage, event)
    assert body["units"] == []
    assert [m["existing_unit_id"] for m in body["merges"]] == [existing_id]
    assert body["questions"] == []


def test_t416b_nothing_in_the_log_names_the_text(
    redis_client: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed(notes=[note(storage, SECRET)])
    with caplog.at_level(logging.DEBUG):
        run(handler(storage, redis_client, stream, sessions, broken_chunker()), event)
    assert SECRET not in caplog.text
    assert "Mitochondria" not in caplog.text


def test_t416b_the_handler_is_registered() -> None:
    from ai_service.handlers import build_handlers

    handlers = build_handlers(redis=None, storage=None, llm=None, sessions=None)  # pyright: ignore[reportArgumentType]
    assert isinstance(handlers["session.confirmed.v1"], ProcessSession)


def test_t416b_overlapping_ranges_read_each_page_once_in_one_batch(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed(ranges=[(DOC, 1, 2), (DOC, 2, 3)])
    run(handler(storage, redis_client, stream, sessions), event)
    assert [type(e) for e in sent(redis_client, stream)][-1] is SessionProcessedEvent
    body = result(storage, event)
    assert sorted(a["page_no"] for u in body["units"] for a in u["anchors"]) == [1, 2, 3]


def test_t416b_overlapping_ranges_across_batches_make_no_duplicate_units(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    pages = {n: f"Page number {n} says something distinct about topic {n}." for n in range(1, 31)}
    index(storage, pages)
    event = confirmed(ranges=[(DOC, 1, 25), (DOC, 5, 30)])
    run(handler(storage, redis_client, stream, sessions), event)
    assert len(result(storage, event)["units"]) == 30


def llm_calls(sessions: sessionmaker[Session]) -> int:
    with sessions() as s:
        return len(s.scalars(select(LlmCall).where(LlmCall.user_id == USER)).all())


def test_t416b_redelivery_after_storage_down_does_not_pay_again(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    h = handler(storage, redis_client, stream, sessions)
    storage.put_error = StorageUnavailable()
    with pytest.raises(Deferred):
        run(h, event)
    paid = llm_calls(sessions)
    assert paid > 0
    storage.put_error = None
    run(h, event)
    assert llm_calls(sessions) == paid
    assert result(storage, event)["questions"]


def test_t416b_redelivery_after_audit_down_keeps_the_chunk_result(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    h = handler(storage, redis_client, stream, sessions)
    real = h._start_run  # pyright: ignore[reportPrivateUsage]
    state = {"fail": True}

    def flaky(ev: SessionConfirmedEvent, task: str, prompt: Any) -> uuid.UUID:
        if task == "generate_questions" and state["fail"]:
            state["fail"] = False
            raise AuditUnavailableError
        return real(ev, task, prompt)

    h._start_run = flaky  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(Deferred):
        run(h, event)
    paid = llm_calls(sessions)
    run(h, event)
    with sessions() as s:
        chunk_calls = s.scalars(
            select(LlmCall).where(LlmCall.user_id == USER, LlmCall.task == "chunk_units")
        ).all()
    assert len(chunk_calls) == paid  # no second chunk_units call
    assert result(storage, event)["questions"]


def test_t416b_a_progress_failure_does_not_fail_the_session(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    h = handler(storage, redis_client, stream, sessions)

    class FlakyRedis:
        def xadd(self, name: str, fields: dict[str, str], **kw: Any) -> Any:
            if "session.progress" in fields["envelope"]:
                raise ConnectionError("redis blinked")
            return redis_client.xadd(name, cast(Any, fields), **kw)

        def __getattr__(self, name: str) -> Any:
            return getattr(redis_client, name)

    h.redis = cast(Redis, FlakyRedis())
    run(h, event)
    assert isinstance(sent(redis_client, stream)[-1], SessionProcessedEvent)


def test_t416b_a_blank_title_drops_that_unit_not_the_session(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)

    def chunk(request: Any) -> str:
        data = json.loads(fake_chunk(request))
        data["units"][0]["title"] = "   "
        return json.dumps(data)

    adapter = FakeAdapter({"chunk_units": chunk, "generate_questions": fake_questions})
    event = confirmed()
    run(handler(storage, redis_client, stream, sessions, adapter), event)
    assert isinstance(sent(redis_client, stream)[-1], SessionProcessedEvent)
    assert len(result(storage, event)["units"]) == 1


def test_t416b_cached_results_are_deleted_after_a_successful_write(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    run(handler(storage, redis_client, stream, sessions), event)
    assert cast(Any, redis_client).keys(f"ai:session:*:{event.event_id}") == []


# --- T5.1b: levels 2 and 3 after level 1 (US-04b, US-02 AC7/AC8, ADR-0010) --------------------


def _levels(body: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {1: [], 2: [], 3: []}
    for q in body["questions"]:
        out[q["level"]].append(q)
    return out


def _not_json(request: Any) -> str:
    return "not json"


def _adapter(higher: Any) -> FakeAdapter:
    def ask(request: Any) -> str:
        return higher(request) if request.prompt_version == "v2" else fake_questions(request)

    return FakeAdapter({"chunk_units": fake_chunk, "generate_questions": ask})


def test_t51b_result_has_level_1_2_and_3_questions(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed(notes=[note(storage)])
    run(handler(storage, redis_client, stream, sessions), event)
    body = result(storage, event)  # validates against session-result.v1
    by_level = _levels(body)
    unit_ids = {u["unit_id"] for u in body["units"]}
    assert len(unit_ids) == 3
    assert {q["unit_ids"][0] for q in by_level[1]} == unit_ids
    assert {q["unit_ids"][0] for q in by_level[2]} == unit_ids
    assert len(by_level[3]) >= 1
    for q in by_level[3]:
        assert len(set(q["unit_ids"])) >= 2 and set(q["unit_ids"]) <= unit_ids
    assert body["dropped"]["questions"] == 0
    with sessions() as s:
        runs = s.scalars(select(PipelineRun).where(PipelineRun.user_id == USER)).all()
    assert sorted((r.task, r.prompt_version) for r in runs) == [
        ("chunk_units", "v1"),
        ("generate_questions", "v1"),
        ("generate_questions", "v2"),
    ]
    assert all(r.status == "succeeded" for r in runs)


def test_t51b_one_unit_gets_level_2_and_no_level_3(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage, {1: PAGE_TEXTS[1]})
    event = confirmed(ranges=[(DOC, 1, 1)])
    run(handler(storage, redis_client, stream, sessions), event)
    by_level = _levels(result(storage, event))
    assert len(by_level[2]) == 1 and by_level[3] == []


def test_t51b_many_units_make_one_higher_call_per_batch(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    pages = {n: f"Page number {n} says something distinct about topic {n}." for n in range(1, 46)}
    index(storage, pages)
    event = confirmed(ranges=[(DOC, 1, 45)])
    run(handler(storage, redis_client, stream, sessions), event)
    with sessions() as s:
        v2 = s.scalars(
            select(LlmCall).where(LlmCall.user_id == USER, LlmCall.prompt_version == "v2")
        ).all()
    assert len(v2) == 3  # 45 units, 20 a batch
    assert len(_levels(result(storage, event))[2]) == 45


def test_t51b_a_failing_higher_call_keeps_level_1_and_records_the_drop(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    adapter = _adapter(_not_json)
    run(handler(storage, redis_client, stream, sessions, adapter), event)
    out = sent(redis_client, stream)
    assert isinstance(out[-1], SessionProcessedEvent)
    body = result(storage, event)
    by_level = _levels(body)
    assert len(by_level[1]) == 2 and by_level[2] == [] and by_level[3] == []
    assert body["dropped"]["questions"] == 2  # the two units left without level 2/3
    with sessions() as s:
        runs = s.scalars(
            select(PipelineRun).where(
                PipelineRun.user_id == USER, PipelineRun.prompt_version == "v2"
            )
        ).all()
    assert [r.status for r in runs] == ["failed"]


def test_t51b_level_3_with_one_unit_is_refused_and_the_batch_dropped(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    def one_unit_level_3(request: Any) -> str:
        labels = request.payload["labels"]
        qs = [
            {"level": 2, "units": [x], "prompt": f"p {x}", "reference_answer": "a", "rubric": "r"}
            for x in labels
        ]
        qs.append(
            {
                "level": 3,
                "units": [labels[0]],
                "prompt": "p3",
                "reference_answer": "a",
                "rubric": "r",
            }
        )
        return json.dumps({"questions": qs})

    storage = FakeStorage()
    index(storage)
    event = confirmed()
    run(handler(storage, redis_client, stream, sessions, _adapter(one_unit_level_3)), event)
    by_level = _levels(result(storage, event))
    assert by_level[3] == [] and by_level[2] == []  # whole higher batch dropped, level 1 kept
    assert len(by_level[1]) == 2


def test_t51b_quota_exceeded_on_the_higher_call_fails_like_level_1(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    class OverOnHigher(NoQuota):
        def reserve(self, request: Any, estimate: Any) -> None:
            if request.prompt_version == "v2":
                raise QuotaExceededError(hard=True, window="day")  # pyright: ignore[reportArgumentType]

    storage = FakeStorage()
    index(storage)
    event = confirmed()
    llm = LlmClient(
        FakeAdapter({"chunk_units": fake_chunk, "generate_questions": fake_questions}),
        sessions,
        models={"chunk_units": "claude-haiku-5-5", "generate_questions": "claude-haiku-5-5"},
        quota_guard=OverOnHigher(),
    )
    h = ProcessSession(
        storage=storage, redis=redis_client, llm=llm, sessions=sessions, stream=stream
    )
    run(h, event)
    out = sent(redis_client, stream)
    assert isinstance(out[-1], SessionFailedEvent) and out[-1].payload.reason == "llm_unavailable"
    assert result_key_for(event) not in storage.objects


def test_t51b_redelivery_after_audit_down_on_the_higher_run_does_not_pay_level_1_again(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    h = handler(storage, redis_client, stream, sessions)
    real = h._start_run  # pyright: ignore[reportPrivateUsage]
    state = {"fail": True}

    def flaky(ev: SessionConfirmedEvent, task: str, prompt: Any) -> uuid.UUID:
        if prompt.version == "v2" and state["fail"]:
            state["fail"] = False
            raise AuditUnavailableError
        return real(ev, task, prompt)

    h._start_run = flaky  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(Deferred):
        run(h, event)
    paid = llm_calls(sessions)
    run(h, event)
    with sessions() as s:
        calls = s.scalars(select(LlmCall).where(LlmCall.user_id == USER)).all()
    kinds = sorted((c.task, c.prompt_version) for c in calls)
    assert kinds.count(("chunk_units", "v1")) == 1
    assert kinds.count(("generate_questions", "v1")) == 1  # level 1 not paid twice
    assert len(calls) == paid + 1  # only the higher call is new
    assert _levels(result(storage, event))[3]


def test_t51b_redelivery_after_storage_down_does_not_pay_again(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    h = handler(storage, redis_client, stream, sessions)
    storage.put_error = StorageUnavailable()
    with pytest.raises(Deferred):
        run(h, event)
    paid = llm_calls(sessions)
    storage.put_error = None
    run(h, event)
    assert llm_calls(sessions) == paid
    assert _levels(result(storage, event))[2]
