"""FIX-CHUNK: draft calls ask for room enough, and a cut answer splits the batch.

QA-FINAL 05/11: `draft_units` v2 hit `stop_reason=max_tokens` at 800 tokens on both attempts,
the cut JSON was refused as `schema`, and the session failed with `model_output`.
"""

from typing import Any

from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ai_service.llm.client import LlmClient
from ai_service.llm.pricing import FAKE_MODEL
from ai_service.llm.types import AdapterResult, LlmRequest, ProviderName
from ai_service.messaging.envelope import SubmissionFailedEvent, SubmissionProcessedEvent
from ai_service.tasks import draft_units
from ai_service.tasks.process_submission import ProcessSubmission
from tests.llm.helpers import NoQuota
from tests.submission.helpers import MODELS, Model, file_of, index, mention, run, submitted
from tests.submission.test_process_submission import result, sent
from tests.tasks.helpers import FakeStorage

TXT = "text/plain"


class CutWhenMany:
    """The fake model, but an answer over `max_pages` document pages is cut at the cap."""

    provider: ProviderName = "fake"
    fixed_model: str | None = FAKE_MODEL
    params: dict[str, Any] = {}

    def __init__(self, max_pages: int) -> None:
        self.inner, self.max_pages = Model().adapter, max_pages
        self.draft_requests: list[LlmRequest] = []

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        out = self.inner.complete(request, model=model, timeout=timeout)
        if request.task != "draft_units":
            return out
        self.draft_requests.append(request)
        pages = [s for s in request.payload["sources"] if s["label"] != "notes"]
        if len(pages) > self.max_pages:
            return AdapterResult(out.text[:40], 0, 0, stop_reason="max_tokens")
        return out


def handler(
    storage: FakeStorage, redis: Redis, stream: str, sessions: sessionmaker[Session], adapter: Any
) -> ProcessSubmission:
    llm = LlmClient(adapter, sessions, models=MODELS, quota_guard=NoQuota())
    return ProcessSubmission(
        storage=storage, redis=redis, llm=llm, sessions=sessions, stream=stream
    )


# Red when: draft calls go out with the 800-token default again (the QA-FINAL root cause).
def test_fix_chunk_draft_calls_ask_for_a_large_output_cap(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    adapter = CutWhenMany(max_pages=99)
    event = submitted(storage, mentions=[mention(1, 3)], files=[file_of(storage, b"x", TXT)])
    run(handler(storage, redis_client, stream, sessions, adapter), event)
    assert adapter.draft_requests
    caps = {r.max_output_tokens for r in adapter.draft_requests}
    assert caps == {draft_units.MAX_OUTPUT_TOKENS}
    assert draft_units.MAX_OUTPUT_TOKENS >= 8192


# Red when: a cut answer is retried as is (same prompt, same cut) or fails the session, instead
# of halving the batch until each part fits.
def test_fix_chunk_cut_answer_halves_the_batch(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    adapter = CutWhenMany(max_pages=1)
    event = submitted(storage, mentions=[mention(1, 3)], files=[file_of(storage, b"x", TXT)])
    run(handler(storage, redis_client, stream, sessions, adapter), event)
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SubmissionProcessedEvent)
    pages = {d["anchors"][0]["page_no"] for d in result(storage, event)["drafts"]}
    assert {1, 2, 3} <= pages
    assert all(r.attempt == 1 for r in adapter.draft_requests)  # a cut is never asked again


# Red when: a single page still cut is not reported as failed (or loops).
def test_fix_chunk_single_page_still_cut_fails_the_submission(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    adapter = CutWhenMany(max_pages=0)
    event = submitted(storage, mentions=[mention(1, 2)], files=[file_of(storage, b"x", TXT)])
    run(handler(storage, redis_client, stream, sessions, adapter), event)
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SubmissionFailedEvent) and out.payload.reason == "internal_error"
    assert len(adapter.draft_requests) == 2  # 2 pages cut, then page 1 cut: stops there
