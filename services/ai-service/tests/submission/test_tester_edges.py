"""T7.7 edge cases found by mutation testing (tester, 01/11): each test here turns red on a
change to `process_submission.py` that every other test let through.

Fake model and fake reader on the real test database and Redis; storage in memory."""

import json
from typing import Any

import pytest
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ai_service.llm import vision
from ai_service.messaging.session_result_v2 import parse_result
from ai_service.tasks import process_submission
from ai_service.tasks import read_notes_image as read_task
from ai_service.tasks.process_submission import result_key_for
from tests.submission.helpers import (
    DOC,
    SEC1,
    SEC2,
    Model,
    file_of,
    handler,
    index,
    mention,
    png,
    run,
    scanned_pdf,
    submitted,
)
from tests.tasks.helpers import FakeStorage

TXT = "text/plain"
PNG = "image/png"


def body_of(storage: FakeStorage, event: Any) -> dict[str, Any]:
    raw = storage.objects[result_key_for(event)]
    parse_result(raw)
    return json.loads(raw)


def doc_labels(model: Model) -> list[str]:
    return [
        s["label"]
        for r in model.calls("draft_units")
        for s in r.payload["sources"]
        if s["label"] != "notes"
    ]


def test_us02_ac11_scope_cap_is_exactly_60_pages_and_the_61st_is_the_note(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: the scope cap lets page 61 through (off by one) or names another page as the
    # first one left out.
    storage = FakeStorage()
    index(storage, {n: f"Trang {n} noi ve khai niem so {n} kha ro rang." for n in range(1, 62)})
    event = submitted(storage, files=[file_of(storage, b"x", TXT)], mentions=[mention(1, 61)])
    model = Model()
    run(handler(storage, redis_client, stream, sessions, model), event)
    assert len(doc_labels(model)) == 60
    body = body_of(storage, event)
    assert {"kind": "page", "ref": 61, "reason": "truncated"} in body["skipped"]
    assert all(a["page_no"] != 61 for d in body["drafts"] for a in d["anchors"])


def test_us02_ac11_a_halved_batch_sends_the_learners_notes_once(
    redis_client: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: the second half of a split batch carries the notes again (the learner's text is
    # paid for twice and its drafts come back twice).
    from ai_service.tasks import chunk_units

    storage = FakeStorage()
    index(storage)
    monkeypatch.setattr(chunk_units, "MAX_PAGES", 1)
    notes = "ghi chu rieng cua nguoi hoc ve ty the va ho hap te bao."
    event = submitted(
        storage, mentions=[mention(1, 3)], files=[file_of(storage, notes.encode(), TXT)]
    )
    model = Model()
    run(handler(storage, redis_client, stream, sessions, model), event)
    with_notes = [
        r
        for r in model.calls("draft_units")
        if any(s["label"] == "notes" for s in r.payload["sources"])
    ]
    assert len(with_notes) == 1
    body = body_of(storage, event)
    notes_anchors = [a for d in body["drafts"] for a in d["anchors"] if a["source"] == "notes"]
    assert len(notes_anchors) == 1


def test_t77_d7_same_quote_in_two_batches_is_one_draft_with_both_anchors(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: drafts of two batches sharing a draft_key are not merged (two drafts with one
    # key break unique(session_id, draft_key) in core), or the merge keeps one batch's anchors.
    storage = FakeStorage()
    same = "Ty the la noi dien ra ho hap te bao o sinh vat nhan thuc."
    pages = {n: f"Trang {n} giai thich mot y khac han so {n}." for n in range(1, 22)}
    pages[1] = pages[21] = same
    index(storage, pages)
    event = submitted(
        storage,
        files=[file_of(storage, b"x", TXT)],
        mentions=[mention(1, 20, SEC1), mention(21, 21, SEC2)],
    )
    model = Model()
    run(handler(storage, redis_client, stream, sessions, model), event)
    assert len(model.calls("draft_units")) == 2  # two batches: 20 pages, then page 21
    body = body_of(storage, event)
    keys = [d["draft_key"] for d in body["drafts"]]
    assert len(keys) == len(set(keys))
    (merged,) = [d for d in body["drafts"] if d["anchors"][0]["quote_text"] == same[:60].strip()]
    assert [(a["document_id"], a["page_no"]) for a in merged["anchors"]] == [
        (str(DOC), 1),
        (str(DOC), 21),
    ]
    assert merged["section_id"] == str(SEC1)


class _SizeSpy(FakeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.limits: dict[str, int] = {}

    def get(self, key: str, *, max_bytes: int) -> bytes:
        self.limits[key] = max_bytes
        return super().get(key, max_bytes=max_bytes)


def test_review_y_e_an_image_file_is_fetched_with_the_vision_byte_budget(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: an image file is fetched with the 30 MB file budget: 20 such files sit in memory
    # at once although shrink refuses anything over vision.MAX_BYTES (review Y-e).
    storage = _SizeSpy()
    index(storage)
    image = file_of(storage, png(3), PNG)
    event = submitted(storage, files=[image])
    run(handler(storage, redis_client, stream, sessions), event)
    assert storage.limits[image["object_key"]] <= vision.MAX_BYTES


def test_us02_ac8_a_long_scanned_pdf_is_not_rendered_past_the_cap(
    redis_client: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: every page of a long scanned PDF is rendered to PNG and held in memory even
    # though only the first 20 are read (CPU and memory of a 300-page scan).
    renders: list[int] = []
    real_open = process_submission.open_pdf

    class _Spy:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def __enter__(self) -> "_Spy":
            self._inner.__enter__()
            return self

        def __exit__(self, *exc: object) -> None:
            self._inner.__exit__(*exc)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

        def render_page(self, index: int, **kw: Any) -> Any:
            renders.append(index)
            return self._inner.render_page(index, **kw)

    def spy_open(data: bytes) -> _Spy:
        return _Spy(real_open(data))

    monkeypatch.setattr(process_submission, "open_pdf", spy_open)
    storage = FakeStorage()
    index(storage)
    event = submitted(storage, files=[file_of(storage, scanned_pdf(30), "application/pdf")])
    model = Model()
    run(handler(storage, redis_client, stream, sessions, model), event)
    assert len(model.calls("read_notes")) == read_task.MAX_IMAGES
    assert len(renders) <= read_task.MAX_IMAGES + 1
