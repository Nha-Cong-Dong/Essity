"""FIX-CHUNK tester edges for a draft answer cut at the output cap (`_split_to_fit`)."""

import logging
from typing import Any

import pytest
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ai_service.llm.types import AdapterResult, LlmRequest
from ai_service.messaging.envelope import SubmissionProcessedEvent
from tests.submission.helpers import file_of, index, mention, run, submitted
from tests.submission.test_fix_chunk_truncation import CutPage, CutWhenMany, handler
from tests.submission.test_process_submission import result, sent
from tests.tasks.helpers import FakeStorage

TXT = "text/plain"


def _dropped_drafts(
    adapter: Any, redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> int:
    storage = FakeStorage()
    index(storage)
    event = submitted(storage, mentions=[mention(1, 3)], files=[file_of(storage, b"x", TXT)])
    run(handler(storage, redis_client, stream, sessions, adapter), event)
    assert isinstance(sent(redis_client, stream)[-1], SubmissionProcessedEvent)
    return int(result(storage, event)["dropped"]["drafts"])


# Red when: a page skipped because its answer is still cut is not counted in `dropped.drafts`
# (the learner's result hides that part of the session made no card), or no `output_cut` line
# is logged for it.
def test_fix_chunk_skipped_cut_page_is_counted_and_logged(
    redis_client: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    whole = _dropped_drafts(CutWhenMany(max_pages=99), redis_client, stream, sessions)
    with caplog.at_level(logging.DEBUG):
        cut = _dropped_drafts(CutPage(page_no=2), redis_client, stream, sessions)
    assert cut == whole + 1
    assert any(getattr(r, "outcome", None) == "output_cut" for r in caplog.records)


class CapHitOnOtherTasks(CutWhenMany):
    """The fake model, but every task other than draft_units reports `stop_reason=max_tokens`
    (its text whole): those tasks keep the adapter's default cap and never ask for their own."""

    def __init__(self) -> None:
        super().__init__(max_pages=99)
        self.tasks: list[str] = []

    def complete(self, request: LlmRequest, *, model: str, timeout: float) -> AdapterResult:
        out = super().complete(request, model=model, timeout=timeout)
        self.tasks.append(request.task)
        if request.task == "draft_units":
            return out
        return AdapterResult(out.text, 0, 0, stop_reason="max_tokens")


# Red when: a task with no cap of its own (merge_drafts) raises `OutputCut` on max_tokens: the
# merge, a convenience, would then fail the whole session and lose its cards.
def test_fix_chunk_cap_hit_on_a_task_without_its_own_cap_keeps_the_cards(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    adapter = CapHitOnOtherTasks()
    event = submitted(storage, mentions=[mention(1, 3)], files=[file_of(storage, b"x", TXT)])
    run(handler(storage, redis_client, stream, sessions, adapter), event)
    assert "merge_drafts" in adapter.tasks
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SubmissionProcessedEvent)
    assert result(storage, event)["drafts"]
