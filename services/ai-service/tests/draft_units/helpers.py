"""Builders for draft_units tests: a request over two documents, and a fake `ask`."""

import json
import uuid
from typing import Any

from ai_service.tasks.chunk_units import ChunkPrompt
from ai_service.tasks.draft_units import DraftRequest, ScopedDoc, ScopedPage

SESSION = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
OTHER_SESSION = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")
DOC1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
DOC2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
SEC1 = uuid.UUID("33333333-3333-3333-3333-333333333333")
SEC2 = uuid.UUID("44444444-4444-4444-4444-444444444444")
P1 = "Mitochondria are the site of cellular respiration in eukaryotic cells. They make ATP."
P2 = "The Krebs cycle oxidises acetyl-CoA to carbon dioxide inside the mitochondrial matrix."
B1 = "ATP synthase uses the proton gradient across the inner membrane to make ATP."
NOTES = "ghi chu: ty the la noi hop ho hap te bao, tao ra nhieu ATP cho te bao."
Q1 = "site of cellular respiration in eukaryotic cells"
Q2 = "Krebs cycle oxidises acetyl-CoA to carbon dioxide"
QB = "ATP synthase uses the proton gradient across the inner membrane"


def request(
    *,
    session_id: uuid.UUID = SESSION,
    notes: str | None = NOTES,
    description: str | None = None,
    pages: list[str] | None = None,
) -> DraftRequest:
    texts = [P1, P2] if pages is None else pages
    return DraftRequest(
        session_id=session_id,
        scope=[
            ScopedDoc(
                document_id=DOC1,
                name="Sinh hoc",
                pages=[
                    ScopedPage(page_no=i, text=t, section_ids=[SEC1])
                    for i, t in enumerate(texts, start=3)
                ],
            ),
            ScopedDoc(
                document_id=DOC2,
                name="Bai giang",
                pages=[ScopedPage(page_no=7, text=B1, section_ids=[SEC2])],
            ),
        ],
        submission_text=notes,
        description=description,
    )


def unit_json(
    title: str = "Ty the",
    anchors: list[tuple[str, str]] | None = None,
    **kw: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": title,
        "summary": "Ty the la noi hop ho hap.",
        "kind": "concept",
        "merge_into": None,
        "lineage": [],
        "anchors": [{"page": p, "quote": q} for p, q in (anchors or [("D1.p3", Q1)])],
    }
    base.update(kw)
    return base


def output(*units: dict[str, Any]) -> str:
    return json.dumps({"units": list(units)})


class FakeAsk:
    """Returns the canned replies in turn (the last one repeats) and records the prompts."""

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.prompts: list[ChunkPrompt] = []

    def __call__(self, prompt: ChunkPrompt) -> str:
        self.prompts.append(prompt)
        reply = self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply
