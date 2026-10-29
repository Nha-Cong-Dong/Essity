"""Builders for chunk_units tests: a request, and a fake `ask` that returns canned JSON."""

import json
import uuid
from typing import Any

from ai_service.tasks.chunk_models import ChunkRequest, DocInput, ExistingUnit, PageInput
from ai_service.tasks.chunk_units import ChunkPrompt

DOC_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
P1 = "Mitochondria are the site of cellular respiration in eukaryotic cells. They make ATP."
P2 = "The Krebs cycle oxidises acetyl-CoA to carbon dioxide inside the mitochondrial matrix."
NOTES = "ghi chu: ty the la noi hop ho hap te bao, tao ra nhieu ATP cho te bao."
Q1 = "site of cellular respiration in eukaryotic cells"
Q2 = "Krebs cycle oxidises acetyl-CoA to carbon dioxide"


def request(
    pages: list[str] | None = None,
    notes: str | None = NOTES,
    existing: list[ExistingUnit] | None = None,
) -> ChunkRequest:
    texts = [P1, P2] if pages is None else pages
    return ChunkRequest(
        documents=[
            DocInput(
                document_id=DOC_ID,
                name="Sinh hoc",
                pages=[PageInput(page_no=i, text=t) for i, t in enumerate(texts, start=1)],
            )
        ],
        notes_text=notes,
        existing_units=existing or [],
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
        "anchors": [{"page": p, "quote": q} for p, q in (anchors or [("D1.p1", Q1)])],
    }
    base.update(kw)
    return base


def output(*units: dict[str, Any]) -> str:
    return json.dumps({"units": list(units)})


class FakeAsk:
    """Returns the canned replies in turn (the last one repeats) and records the prompts."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[ChunkPrompt] = []

    def __call__(self, prompt: ChunkPrompt) -> str:
        self.prompts.append(prompt)
        i = min(len(self.prompts) - 1, len(self.replies) - 1)
        return self.replies[i]
