"""CARDS-V3: drafts that say the same thing become one card, the session gets a topic title, and an
empty result says why. Fake model, in-memory storage."""

import json
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ai_service.clients.storage import StorageUnavailable
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import LlmRequest
from ai_service.messaging.consumer import Deferred
from ai_service.messaging.session_result_v2 import draft_key_for_set, quote_hash
from ai_service.tasks.draft_units import Draft, DraftAnchor
from ai_service.tasks.merge_drafts import clean_title, combine, key_of
from tests.submission.helpers import PAGES, Model, again, file_of, handler, index, mention, run
from tests.submission.helpers import submitted as submit
from tests.submission.test_process_submission import result
from tests.tasks.helpers import FakeStorage

TXT = "text/plain"


def merge_of(groups: list[list[str]], **more: Any) -> Callable[[LlmRequest], str]:
    def answer(request: LlmRequest) -> str:
        return json.dumps({"groups": groups, **more})

    return answer


def go(
    redis: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    model: Model,
    *,
    pages: tuple[int, int] | None = (1, 2),
    notes: bytes | None = None,
    quota: Any = None,
) -> tuple[dict[str, Any], FakeStorage]:
    storage = FakeStorage()
    index(storage)
    files = [file_of(storage, notes, TXT)] if notes else None
    event = submit(
        storage,
        files=files,
        mentions=[mention(pages[0], pages[1])] if pages else [],
    )
    run(handler(storage, redis, stream, sessions, model, quota=quota), event)
    return result(storage, event), storage


def test_two_sources_one_card(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: the same knowledge from two sources comes out as two cards.
    model = Model(merge=merge_of([["C1", "C2"]], title="Tế bào học"))
    body, _ = go(redis_client, stream, sessions, model)
    assert len(body["drafts"]) == 1  # pages 1 and 2 (no notes file text beyond the default)
    (draft,) = body["drafts"]
    assert {a["page_no"] for a in draft["anchors"]} == {1, 2}
    assert len(model.calls("merge_drafts")) == 1


def test_merged_draft_key_is_over_the_set_of_quotes_and_validates(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    model = Model(merge=merge_of([["C1", "C2"]]))
    body, _ = go(redis_client, stream, sessions, model)
    (draft,) = body["drafts"]
    sid = uuid.UUID(body["study_session_id"])
    hashes = [quote_hash(a["quote_text"]) for a in draft["anchors"]]
    assert draft["draft_key"] == draft_key_for_set(sid, hashes)
    assert draft["quote_hash"] == hashes[0]


def anchor(page: int, quote: str) -> DraftAnchor:
    return DraftAnchor(uuid.UUID(int=7), page, quote, 0, len(quote))


def draft_of(title: str, content: str, *anchors: DraftAnchor) -> Draft:
    return Draft("k", quote_hash(anchors[0].quote), title, content, "concept", [], list(anchors))


def test_draft_key_stable_over_reorder() -> None:
    # Red when: the key depends on the order the anchors are listed in.
    sid = uuid.UUID(int=1)
    a, b = anchor(1, "aaa"), anchor(2, "bbb")
    assert key_of(sid, draft_of("t", "c", a, b)) == key_of(sid, draft_of("t", "c", b, a))
    assert key_of(sid, draft_of("t", "c", a)) == draft_key_for_set(sid, [quote_hash("aaa")])


def test_combine_takes_one_candidates_text_and_every_anchor() -> None:
    a, b = anchor(1, "aaa"), anchor(2, "bbb")
    merged = combine([draft_of("A", "short", a), draft_of("B", "a much longer content", b)])
    assert (merged.title, merged.content) == ("B", "a much longer content")
    assert [x.quote for x in merged.anchors] == ["aaa", "bbb"]


def test_merge_failure_keeps_unmerged_drafts(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: a broken answer loses or fails the cards.
    for answer in ("not json", '{"groups": "x"}', "{" + '"groups": [],' * 2000):
        model = Model(merge=lambda request, a=answer: a)
        body, _ = go(redis_client, stream, sessions, model)
        assert len(body["drafts"]) == 2


class CappedMerge:
    """The cost cap reached for the merge call only."""

    def reserve(self, request: LlmRequest, estimate: Decimal) -> uuid.UUID | None:
        if request.task == "merge_drafts":
            raise QuotaExceededError(hard=False, window="day")
        return None

    def release(self, reservation_id: uuid.UUID, session: Session | None = None) -> None:
        return None

    def hold(self, reservation_id: uuid.UUID) -> None:
        return None


def test_merge_quota_exhausted_keeps_drafts(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    body, _ = go(redis_client, stream, sessions, Model(), quota=CappedMerge())
    assert len(body["drafts"]) == 2 and "notice" not in body


def test_merge_unknown_index_ignored(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    model = Model(merge=merge_of([["C1", "C99"], ["C2", "C2"], ["C1", "C2", "C1"]]))
    body, _ = go(redis_client, stream, sessions, model)
    # the third group is the only real one: C1 and C2 (the repeat of C1 is ignored)
    assert len(body["drafts"]) == 1


def test_merge_cannot_add_anchor_or_text(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: the model can put its own words or quotes into a card that goes straight to the Kho.
    forged = merge_of([["C1", "C2"]], content="Bịa ra", anchors=[{"quote": "Bịa"}])
    body, _ = go(redis_client, stream, sessions, Model(merge=forged))
    assert len(body["drafts"]) == 2  # an answer with fields outside the schema is refused whole
    ok, _ = go(redis_client, stream, sessions, Model(merge=merge_of([["C1", "C2"]])))
    (draft,) = ok["drafts"]
    assert draft["content"] in set(PAGES.values()) | {p[:60] for p in PAGES.values()}
    for a in draft["anchors"]:
        assert a["quote_text"] in PAGES[a["page_no"]]


def test_result_has_topic_title(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    body, _ = go(redis_client, stream, sessions, Model(merge=merge_of([], title="  Tế bào\nhọc  ")))
    assert body["title"] == "Tế bào học"


def test_title_is_cleaned_and_bounded() -> None:
    assert clean_title("a\x00b\x1fc " + "x" * 500) is not None
    cleaned = clean_title("a\x00b\x1fc " + "x" * 500)
    assert cleaned is not None and len(cleaned) <= 200 and "\x00" not in cleaned
    assert clean_title("   ") is None and clean_title(None) is None


def test_unusable_title_falls_back_to_the_first_draft_title(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    body, _ = go(redis_client, stream, sessions, Model(merge=merge_of([], title="  \x00 ")))
    assert body["title"] == body["drafts"][0]["title"]


def test_single_draft_makes_no_merge_call_and_names_the_session_by_it(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    model = Model()
    body, _ = go(redis_client, stream, sessions, model, pages=None, notes=b"mot ghi chu ve ty the")
    assert model.calls("merge_drafts") == [] and len(body["drafts"]) == 1
    assert body["title"] == body["drafts"][0]["title"]


def test_zero_cards_sets_notice(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: nothing was found and the result says nothing.
    model = Model(draft=lambda request: json.dumps({"units": []}))
    body, _ = go(redis_client, stream, sessions, model)
    assert body["drafts"] == [] and body["notice"] == "no_content_found"
    assert "title" not in body and model.calls("merge_drafts") == []


def test_notice_is_absent_when_cards_exist(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    body, _ = go(redis_client, stream, sessions, Model())
    assert "notice" not in body


def test_rerun_after_a_failed_put_makes_no_second_merge_call(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    # Red when: a retry asks the merge again and may group differently (a second card).
    storage = FakeStorage()
    index(storage)
    event = submit(storage, mentions=[mention(1, 2)])
    model = Model(merge=merge_of([["C1", "C2"]], title="T"))
    h = handler(storage, redis_client, stream, sessions, model)
    original = storage.put

    def put(key: str, data: bytes, *, content_type: str) -> None:
        if "/result-" in key:
            raise StorageUnavailable
        original(key, data, content_type=content_type)

    storage.put = put
    with pytest.raises(Deferred):
        run(h, event)
    calls = len(model.requests)
    storage.put = original
    run(h, again(event))
    assert len(model.requests) == calls
    assert len(result(storage, event)["drafts"]) == 1
