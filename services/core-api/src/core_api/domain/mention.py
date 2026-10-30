"""`@name` mentions in a submission's description, resolved without AI (T7.6, US-02 AC3, AC4).

Pure: the caller hands in the subject's indexed documents and their outlines. The same input
always gives the same output; a name or scope that does not resolve is an error naming the part,
never a guess. The grammar is the one in the branch plan (decision table, "Ngữ pháp `@`"):

    @<document short name> [<scope>] [and <scope>]...
    scope = chapter|chương N | mục A.B[.C] | tr.|trang|p. N[-M] | slide N[-M]

The name is the longest prefix of the text after `@` that equals a document's short name, folded
(case, accents, runs of spaces). The scope ends at the next mention, a line break or `;`. No scope
phrase means the whole document.
"""

import re
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

MAX_MENTIONS = 20


class MentionError(Exception):
    """A mention that does not resolve. `part` is the piece of the learner's text that did not
    (it goes into the response, never into a log), `mention` the index of the mention."""

    def __init__(
        self,
        code: str,
        mention: int,
        part: str,
        candidates: Sequence[uuid.UUID] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.mention = mention
        self.part = part
        self.candidates = tuple(candidates)


@dataclass(frozen=True)
class DocInfo:
    id: uuid.UUID
    short_name: str
    format: str
    page_count: int
    # Printed page label of file page i + 1, when the document has labels.
    page_labels: Sequence[str] | None = None


@dataclass(frozen=True)
class SectionInfo:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    ord: int
    title: str
    first_page: int | None = None
    last_page: int | None = None


@dataclass(frozen=True)
class ExplicitMention:
    """A mention the client already pointed at a document (`start` is the index of its `@`)."""

    document_id: uuid.UUID
    start: int
    end: int


@dataclass(frozen=True)
class ResolvedMention:
    index: int
    document_id: uuid.UUID
    section_id: uuid.UUID | None
    first_page: int | None
    last_page: int | None


_SPECIAL = {"đ": "d", "Đ": "d", "–": "-", "—": "-", "−": "-"}


def _fold_char(char: str) -> str:
    if char in _SPECIAL:
        return _SPECIAL[char]
    decomposed = unicodedata.normalize("NFD", char)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def fold(text: str) -> str:
    """Lower case, no accents, dashes as `-`, runs of white space as one space, trimmed."""
    folded = "".join(_fold_char(c) for c in text)
    return re.sub(r"\s+", " ", folded).strip()


def _is_word(char: str) -> bool:
    return char.isalnum()


def _mention_starts(text: str) -> list[int]:
    """Indexes of each `@` that begins a mention: not inside a word (an e-mail address)."""
    return [
        i for i, char in enumerate(text) if char == "@" and (i == 0 or not _is_word(text[i - 1]))
    ]


def _segment_end(text: str, start: int, starts: Sequence[int]) -> int:
    ends = [len(text)]
    ends += [s for s in starts if s > start]
    for stop in ("\n", ";"):
        found = text.find(stop, start)
        if found != -1:
            ends.append(found)
    return min(ends)


# --- Name -------------------------------------------------------------------------------------


def _match_document(
    mention: int, folded_rest: str, documents: Sequence[DocInfo]
) -> tuple[DocInfo, str]:
    """The document whose folded short name is the longest prefix of `folded_rest`, and what
    follows the name."""
    best: list[DocInfo] = []
    best_len = 0
    for document in documents:
        name = fold(document.short_name)
        if not name or not folded_rest.startswith(name):
            continue
        after = folded_rest[len(name) :]
        if after and _is_word(after[0]) and _is_word(name[-1]):
            continue
        if len(name) > best_len:
            best, best_len = [document], len(name)
        elif len(name) == best_len:
            best.append(document)
    if not best:
        raise MentionError("mention_not_found", mention, folded_rest.split(" ")[0][:60])
    if len(best) > 1:
        raise MentionError(
            "mention_ambiguous",
            mention,
            folded_rest[:best_len],
            sorted(d.id for d in best),
        )
    return best[0], folded_rest[best_len:]


# --- Scope ------------------------------------------------------------------------------------

_NUM = r"\d+(?:\.\d+)*"
_LIST_SEP = r"\s*(?:,|va|and)\s*"
_CHAPTER = re.compile(rf"(?:chuong|chapter|ch\.?)\s*({_NUM}(?:{_LIST_SEP}{_NUM})*)")
_SECTION = re.compile(rf"(?:muc|section)\s*({_NUM}(?:{_LIST_SEP}{_NUM})*)")
_RANGE = r"\d+(?:\s*-\s*\d+)?"
_PAGES = re.compile(rf"(?:trang|tr\.?|pp?\.?|page)\s*({_RANGE}(?:{_LIST_SEP}{_RANGE})*)")
_SLIDES = re.compile(rf"(?:slide|slides)\s*({_RANGE}(?:{_LIST_SEP}{_RANGE})*)")
_SEP = re.compile(_LIST_SEP)


@dataclass(frozen=True)
class _Scope:
    kind: str
    items: list[str]
    text: str


def _parse_scope(rest: str) -> _Scope | None:
    """The scope phrase at the start of the folded text after the name, if there is one."""
    rest = rest.lstrip(" ,:")
    for kind, pattern in (
        ("chapter", _CHAPTER),
        ("section", _SECTION),
        ("slide", _SLIDES),
        ("page", _PAGES),
    ):
        found = pattern.match(rest)
        if found:
            items = [item.strip() for item in _SEP.split(found.group(1))]
            return _Scope(kind, items, found.group(0))
    return None


def _number_prefix(title: str) -> str | None:
    """The number a section title starts with ("Chương 3. Mạng" -> "3", "2.1 Định tuyến" ->
    "2.1"), after an optional word such as chương, mục, chapter, phần, bài."""
    folded = fold(title)
    found = re.match(rf"(?:[a-z]+\.?\s+)?({_NUM})(?![0-9])", folded)
    return found.group(1) if found else None


def _children(sections: Sequence[SectionInfo], parent: uuid.UUID | None) -> list[SectionInfo]:
    return sorted((s for s in sections if s.parent_id == parent), key=lambda s: (s.ord, str(s.id)))


def _section_scope(
    mention: int, kind: str, number: str, sections: Sequence[SectionInfo], text: str
) -> SectionInfo:
    pool = _children(sections, None) if kind == "chapter" else list(sections)
    numbered = [(s, _number_prefix(s.title)) for s in pool]
    if any(n is not None for _, n in numbered):
        hits = [s for s, n in numbered if n == number]
        if len(hits) > 1:
            raise MentionError("scope_ambiguous", mention, text, sorted(s.id for s in hits))
        if hits:
            return hits[0]
        raise MentionError("scope_not_found", mention, text)
    # No title carries a number: count by position in the tree.
    current: SectionInfo | None = None
    for step in number.split("."):
        siblings = _children(sections, current.id if current else None)
        position = int(step)
        if not 1 <= position <= len(siblings) or (kind == "chapter" and "." in number):
            raise MentionError("scope_not_found", mention, text)
        current = siblings[position - 1]
    if current is None:
        raise MentionError("scope_not_found", mention, text)
    return current


def _page_position(document: DocInfo, number: int) -> int | None:
    """File position of a page number: the printed label when the document has labels."""
    if document.page_labels is None:
        return number if 1 <= number <= document.page_count else None
    for position, label in enumerate(document.page_labels, start=1):
        if label == str(number):
            return position
    return None


def _page_range(mention: int, document: DocInfo, item: str, text: str) -> tuple[int, int]:
    bounds = [int(n) for n in re.split(r"\s*-\s*", item)]
    first, last = bounds[0], bounds[-1]
    if first > last:
        raise MentionError("scope_out_of_range", mention, text)
    start, end = _page_position(document, first), _page_position(document, last)
    if start is None or end is None or start > end:
        raise MentionError("scope_out_of_range", mention, text)
    return start, end


def _resolve_scope(
    mention: int,
    document: DocInfo,
    sections: Sequence[SectionInfo],
    scope: _Scope | None,
    first_index: int,
) -> list[ResolvedMention]:
    if scope is None:
        return [ResolvedMention(first_index, document.id, None, None, None)]
    if scope.kind == "slide" and document.format != "pptx":
        raise MentionError("scope_unsupported", mention, scope.text)
    resolved: list[ResolvedMention] = []
    for offset, item in enumerate(scope.items):
        index = first_index + offset
        if scope.kind in ("chapter", "section"):
            section = _section_scope(mention, scope.kind, item, sections, scope.text)
            resolved.append(
                ResolvedMention(
                    index, document.id, section.id, section.first_page, section.last_page
                )
            )
        else:
            first, last = _page_range(mention, document, item, scope.text)
            resolved.append(ResolvedMention(index, document.id, None, first, last))
    return resolved


# --- Entry point ------------------------------------------------------------------------------


def resolve_mentions(
    description: str,
    documents: Sequence[DocInfo],
    sections: Mapping[uuid.UUID, Sequence[SectionInfo]],
    explicit: Sequence[ExplicitMention] = (),
) -> list[ResolvedMention]:
    """Every mention of `description`, in order. `documents` are the subject's indexed ones.

    Raises `MentionError` on the first mention that does not resolve. An `explicit` mention takes
    its document by id (the name in the text is not looked up), its scope from the text after it.
    """
    by_id = {d.id: d for d in documents}
    starts = _mention_starts(description)
    pointed = {e.start: e for e in explicit}
    resolved: list[ResolvedMention] = []
    for mention, start in enumerate(starts):
        end = _segment_end(description, start, starts)
        explicit_mention = pointed.get(start)
        if explicit_mention is not None:
            document = by_id.get(explicit_mention.document_id)
            if document is None or not start < explicit_mention.end <= end:
                raise MentionError("mention_not_found", mention, description[start + 1 : end][:60])
            cut = explicit_mention.end - start - 1
            after = fold(description[start + 1 + cut : end])
            after = " " + after if after else ""
        else:
            document, after = _match_document(
                mention, fold(description[start + 1 : end]), documents
            )
        scope = _parse_scope(after)
        resolved += _resolve_scope(
            mention, document, sections.get(document.id, ()), scope, len(resolved)
        )
    if len(resolved) > MAX_MENTIONS:
        raise MentionError("too_many_mentions", MAX_MENTIONS, "")
    return resolved
