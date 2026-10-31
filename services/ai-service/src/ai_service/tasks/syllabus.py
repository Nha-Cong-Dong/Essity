"""Syllabus tree of a textbook (T7.2, v2 §5): the table of contents as nodes with page ranges.

The core is pure: `build_syllabus(page_count, outline, pages, ask)` where `ask` sends a
`SyllabusPrompt` to the model and returns its text. `SyllabusAsker` binds `ask` to `LlmClient`
(quota guard, audit row) and `outline_file` is the file the indexing pipeline writes for core-api
(T7.4).

Sources, tried in order, the first usable one wins:
  1. `bookmarks`: the PDF outline;
  2. `regex`: lines "Chuong N" / "Chapter N" at the top of a page;
  3. `llm_toc`: the model reads one to three table-of-contents pages (only when such a page is
     found, so a book without one costs nothing);
  4. `chunk10`: blocks of 10 pages, a temporary tree.

Every source ends in the same shape: leaves are contiguous, cover pages 1..page_count and carry
weight = their page count. A node's `weight` is the pages under it. The model's output is
untrusted: checked by schema and size here, and any failure of it, or of `ask`, falls through to
`chunk10`. Nothing here logs a title or a page's text.
"""

import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, update

from ai_service.db.models import PipelineRun
from ai_service.db.session import SessionFactory
from ai_service.llm.client import AuditUnavailableError, LlmClient
from ai_service.llm.types import LlmRequest
from ai_service.pdf import OutlineEntry, PageText
from ai_service.tasks.grade import new_nonce, wrap_untrusted

_log = logging.getLogger(__name__)

TASK = "syllabus_toc"
PROMPT_VERSION = "v1"
CALL_SECONDS = 60.0
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"
ATTEMPTS = 2
CHUNK_PAGES = 10
MAX_NODES = 2000
MAX_TITLE_CHARS = 200
MAX_LEVEL = 3
MAX_OUTPUT_CHARS = 100_000
# The table of contents is looked for in the front of the book, and read at most this many pages.
TOC_SEARCH_PAGES = 30
TOC_READ_PAGES = 3
MAX_TOC_PAGE_CHARS = 12_000
FRONT_MATTER_TITLE = "Front matter"

Source = Literal["bookmarks", "regex", "llm_toc", "chunk10"]

# The keyword must stand alone on its line, so prose that mentions "contents" does not match.
_TOC_WORDS = re.compile(
    r"^\s*(?:m[uụ]c\s+l[uụ]c|table\s+of\s+contents|contents)\s*:?\s*$",
    re.I | re.M,
)
_CHAPTER = re.compile(r"^\s*(?:ch[uư][oơ]ng|chapter)\s+(\d+|[ivxlc]+)\b", re.I)
_HEADING_LINES = 6
_MAX_HEADING_CHARS = 120
# Shorter titles ("1", "A") would match any page when looking for the page offset.
_MIN_MATCH_CHARS = 4
_LISTING_LINES = 40


@dataclass(frozen=True)
class SyllabusNode:
    title: str
    # 0 for a chapter or part.
    level: int
    # Position in the tree, depth first from 0.
    ord: int
    # 1-based, inclusive.
    page_start: int
    page_end: int
    # Pages under the node: for leaves, page_end - page_start + 1.
    weight: int
    unit: Literal["page"] = "page"
    source: Source = "chunk10"

    @property
    def temporary(self) -> bool:
        """A chunk10 tree is a stand-in until the learner fixes the syllabus."""
        return self.source == "chunk10"


@dataclass(frozen=True)
class SyllabusPrompt:
    system: str
    user: str
    output_schema: dict[str, Any]
    nonce: str


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise ValueError("NUL")
    return text


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("blank")
    return text


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class LlmTocEntry(_Strict):
    title: Annotated[
        str,
        AfterValidator(_no_nul),
        AfterValidator(_not_blank),
        Field(max_length=MAX_TITLE_CHARS),
    ]
    level: Annotated[int, Field(ge=0, le=MAX_LEVEL)]
    page: Annotated[int, Field(ge=1, le=100_000)]


class LlmToc(_Strict):
    entries: Annotated[list[LlmTocEntry], Field(max_length=MAX_NODES)]


OUTPUT_SCHEMA: dict[str, Any] = LlmToc.model_json_schema()


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str
    sha256: str


@lru_cache
def load_prompt(version: str = PROMPT_VERSION) -> Prompt:
    text = (_PROMPTS / "syllabus_toc" / f"{version}.md").read_text("utf-8")
    return Prompt(version=version, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


# (title, level, 0-based first page)
_Heading = tuple[str, int, int]


def _single_line(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()[:MAX_TITLE_CHARS]


def _tidy(headings: Sequence[_Heading], page_count: int) -> list[_Heading]:
    """Sort by page (stable), drop what points nowhere, make levels a tree (the first is 0, none
    jumps down by more than one), and drop a heading that shares its page with a later one that
    is not inside it: that heading would own no page."""
    kept = [
        (_single_line(title), max(0, level), page)
        for title, level, page in headings
        if 0 <= page < page_count and _single_line(title)
    ]
    kept.sort(key=lambda h: h[2])
    fixed: list[_Heading] = []
    previous = -1
    for title, level, page in kept:
        level = min(level, previous + 1, MAX_LEVEL)
        fixed.append((title, level, page))
        previous = level
    # Back to front, against the nearest heading kept after it, so a run of headings on one page
    # collapses to the ones that nest.
    result: list[_Heading] = []
    for heading in reversed(fixed):
        following = result[-1] if result else None
        if following and following[2] == heading[2] and following[1] <= heading[1]:
            continue
        result.append(heading)
    result.reverse()
    return result


def _tree(headings: Sequence[_Heading], page_count: int, source: Source) -> list[SyllabusNode]:
    """Nodes in depth-first order from tidy headings. Pages before the first heading become a
    front-matter leaf; a heading whose first child starts after it keeps its own first pages as
    a child with its own title, so the leaves always tile 1..page_count."""
    items: list[_Heading] = list(headings)
    if items[0][2] > 0:
        items.insert(0, (FRONT_MATTER_TITLE, 0, 0))
    n = len(items)
    drafts: list[tuple[str, int, int, int]] = []  # title, level, start, end (exclusive)
    for index, (title, level, start) in enumerate(items):
        end = page_count
        for later in items[index + 1 :]:
            if later[1] <= level:
                end = later[2]
                break
        drafts.append((title, level, start, end))
        if index + 1 < n and items[index + 1][1] > level and items[index + 1][2] > start:
            drafts.append((title, level + 1, start, items[index + 1][2]))
    return [
        SyllabusNode(
            title=title,
            level=level,
            ord=order,
            page_start=start + 1,
            page_end=end,
            weight=end - start,
            source=source,
        )
        for order, (title, level, start, end) in enumerate(drafts)
    ]


def _from_bookmarks(outline: Sequence[OutlineEntry], page_count: int) -> list[_Heading] | None:
    headings = [
        (entry.title, entry.level, entry.page_index)
        for entry in outline
        if entry.page_index is not None
    ]
    tidy = _tidy(headings, page_count)
    return tidy if len(tidy) >= 2 else None


def _is_listing(lines: Sequence[str]) -> bool:
    """A page naming two or more chapters in its first lines lists them (a contents page)."""
    names = {
        m.group(1).casefold() for line in lines[:_LISTING_LINES] if (m := _CHAPTER.match(line))
    }
    return len(names) >= 2


def _from_regex(pages: Sequence[PageText], page_count: int) -> list[_Heading] | None:
    found: dict[str, _Heading] = {}
    for index, page in enumerate(pages[:page_count]):
        lines = page.text.splitlines()
        if _TOC_WORDS.search(page.text[:400]) or _is_listing(lines):
            continue
        for line in lines[:_HEADING_LINES]:
            match = _CHAPTER.match(line)
            if match and len(line.strip()) <= _MAX_HEADING_CHARS:
                # The first mention outside the contents pages is where the chapter starts;
                # later ones are running headers.
                found.setdefault(match.group(1).casefold(), (line.strip(), 0, index))
                break
    tidy = _tidy(list(found.values()), page_count)
    return tidy if len(tidy) >= 2 else None


def _toc_pages(pages: Sequence[PageText]) -> list[int]:
    for index, page in enumerate(pages[:TOC_SEARCH_PAGES]):
        if _TOC_WORDS.search(page.text[:400]):
            return list(range(index, min(index + TOC_READ_PAGES, len(pages))))
    return []


def build_prompt(pages: Sequence[PageText], toc_pages: Sequence[int]) -> SyllabusPrompt:
    texts = [pages[index].text[:MAX_TOC_PAGE_CHARS] for index in toc_pages]
    nonce = new_nonce()
    while any(nonce in text for text in texts):
        nonce = new_nonce()
    blocks = [
        wrap_untrusted("toc", text, nonce, label=f"T{n}") for n, text in enumerate(texts, start=1)
    ]
    system = load_prompt().text.replace(_NONCE_PLACEHOLDER, nonce)
    return SyllabusPrompt(system, "\n\n".join(blocks), OUTPUT_SCHEMA, nonce)


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text).strip().casefold()


def _page_offset(entries: Sequence[LlmTocEntry], pages: Sequence[PageText], after: int) -> int:
    """Printed page minus file page, from the first entry whose title heads a page after the
    contents pages. 0 when none is found (printed numbers then are taken as file numbers)."""
    for entry in entries[:10]:
        title = _norm(entry.title)
        if len(title) < _MIN_MATCH_CHARS:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(title)}(?!\w)")
        for index in range(after, len(pages)):
            head = _norm(" ".join(pages[index].text.splitlines()[:_HEADING_LINES]))
            if pattern.search(head):
                return entry.page - (index + 1)
    return 0


def _from_llm(
    pages: Sequence[PageText], page_count: int, ask: Callable[[SyllabusPrompt], str]
) -> list[_Heading] | None:
    toc_pages = _toc_pages(pages)
    if not toc_pages:
        return None
    prompt = build_prompt(pages, toc_pages)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            text = ask(prompt)
        except Exception as error:  # quota, provider, network: the type only, never a message
            _log.warning(
                "syllabus toc call failed",
                extra={"outcome": type(error).__name__, "attempt": attempt},
            )
            return None
        try:
            if len(text) > MAX_OUTPUT_CHARS:
                raise ValueError("too_long")
            toc = LlmToc.model_validate_json(text)
        except (ValidationError, ValueError):
            _log.warning("syllabus toc output refused", extra={"attempt": attempt})
            continue
        offset = _page_offset(toc.entries, pages, toc_pages[-1] + 1)
        headings = [(e.title, e.level, e.page - offset - 1) for e in toc.entries]
        tidy = _tidy(headings, page_count)
        if len(tidy) >= 2:
            return tidy
        _log.warning("syllabus toc output unusable", extra={"attempt": attempt})
        return None
    return None


def _tiles(nodes: Sequence[SyllabusNode], page_count: int) -> bool:
    """The invariant every source must meet: leaves contiguous over 1..page_count, no empty node."""
    if not nodes or any(n.page_end < n.page_start or n.weight < 1 for n in nodes):
        return False
    leaves = [
        n for i, n in enumerate(nodes) if i + 1 == len(nodes) or nodes[i + 1].level <= n.level
    ]
    expected = 1
    for leaf in leaves:
        if leaf.page_start != expected:
            return False
        expected = leaf.page_end + 1
    return expected == page_count + 1


def chunk10(page_count: int) -> list[SyllabusNode]:
    nodes: list[SyllabusNode] = []
    for order, start in enumerate(range(0, page_count, CHUNK_PAGES)):
        end = min(start + CHUNK_PAGES, page_count)
        nodes.append(
            SyllabusNode(
                title=f"Pages {start + 1}-{end}",
                level=0,
                ord=order,
                page_start=start + 1,
                page_end=end,
                weight=end - start,
                source="chunk10",
            )
        )
    return nodes


def build_syllabus(
    page_count: int,
    outline: Sequence[OutlineEntry],
    pages: Sequence[PageText],
    ask: Callable[[SyllabusPrompt], str],
) -> list[SyllabusNode]:
    """The syllabus tree of one document. Never raises for what the file or the model holds:
    the worst case is the temporary `chunk10` tree."""
    if page_count < 1:
        return []
    candidates: list[tuple[Source, Callable[[], list[_Heading] | None]]] = [
        ("bookmarks", lambda: _from_bookmarks(outline, page_count)),
        ("regex", lambda: _from_regex(pages, page_count)),
        ("llm_toc", lambda: _from_llm(pages, page_count, ask)),
    ]
    for source, find in candidates:
        headings = find()
        if headings:
            nodes = _tree(headings, page_count, source)
            if len(nodes) <= MAX_NODES and _tiles(nodes, page_count):
                return nodes
    return chunk10(page_count)


# Source names in core-api's `doc_section.source` vocabulary (a "regex" tree is found by headings).
_SECTION_SOURCE: dict[Source, str] = {
    "bookmarks": "bookmark",
    "regex": "heading",
    "llm_toc": "llm_toc",
    "chunk10": "chunk10",
}


def outline_file(nodes: Sequence[SyllabusNode]) -> dict[str, Any]:
    """The `outline.json` body core-api reads: nodes depth first, each with the index of its
    parent (None for a root). Core owns the rules for what it accepts."""
    parents: list[int | None] = []
    stack: list[int] = []
    for index, node in enumerate(nodes):
        del stack[node.level :]
        parents.append(stack[-1] if stack else None)
        stack.append(index)
    return {
        "unit": "page",
        "nodes": [
            {
                "title": node.title,
                "parent": parent,
                "page_start": node.page_start,
                "page_end": node.page_end,
                "weight": node.weight,
                "source": _SECTION_SOURCE[node.source],
            }
            for node, parent in zip(nodes, parents, strict=True)
        ],
    }


def fake_toc(request: LlmRequest) -> str:
    """The fake provider's answer: no entries, so the tree falls through to `chunk10`."""
    return json.dumps({"entries": []})


class SyllabusAsker:
    """Binds `build_syllabus`'s `ask` to LlmClient. The `pipeline_run` row is written on the first
    call only, so a book that needs no model leaves no run; `finish` closes it. Never raises from
    `finish`: the tree is already built."""

    def __init__(
        self,
        llm: LlmClient,
        sessions: SessionFactory,
        *,
        user_id: uuid.UUID,
        subject_id: uuid.UUID,
    ) -> None:
        self.llm, self.sessions = llm, sessions
        self.user_id, self.subject_id = user_id, subject_id
        self.calls = 0
        self._run_id: uuid.UUID | None = None
        self._error: str | None = None

    def __call__(self, prompt: SyllabusPrompt) -> str:
        if self._run_id is None:
            self._run_id = self._start_run()
        self.calls += 1
        request = LlmRequest(
            task=TASK,
            user_id=self.user_id,
            subject_id=self.subject_id,
            pipeline_run_id=self._run_id,
            prompt_version=PROMPT_VERSION,
            attempt=min(self.calls, 2),
            system=prompt.system,
            user=prompt.user,
            output_schema=prompt.output_schema,
        )
        try:
            return self.llm.call(request, deadline=time.monotonic() + CALL_SECONDS).text
        except Exception as error:
            self._error = type(error).__name__[:60]
            raise

    def _start_run(self) -> uuid.UUID:
        prompt = load_prompt()
        run = PipelineRun(
            user_id=self.user_id,
            subject_id=self.subject_id,
            task=TASK,
            prompt_version=prompt.version,
            prompt_sha256=prompt.sha256,
        )
        try:
            with self.sessions() as session:
                session.add(run)
                session.commit()
        except Exception as error:
            _log.exception("pipeline_run not written")
            raise AuditUnavailableError from error
        return run.id

    def finish(self) -> None:
        if self._run_id is None:
            return
        try:
            with self.sessions() as session:
                session.execute(
                    update(PipelineRun)
                    .where(PipelineRun.id == self._run_id)
                    .values(
                        status="failed" if self._error else "succeeded",
                        error_code=self._error,
                        finished_at=func.now(),
                    )
                )
                session.commit()
        except Exception:
            _log.exception("pipeline_run not closed")
