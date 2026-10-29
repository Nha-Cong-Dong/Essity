"""Anchor check (T4.15, US-02b AC3): the code, never the model, decides a quote is in the text.

A quote is looked up in the page text after NFC and whitespace folding (case kept). Offsets
are Python code points into the ORIGINAL text, so `text[start:end]` is what the learner sees.
Pure: no I/O.
"""

import re
import unicodedata

# Below this a quote proves nothing ("là"); flow-expert 29/10.
MIN_QUOTE_CHARS = 15

Span = tuple[int, int]


def _clusters(text: str) -> list[Span]:
    """Split into [start, end) runs: a base char plus its combining marks, or a whitespace run."""
    spans: list[Span] = []
    i, n = 0, len(text)
    while i < n:
        j = i + 1
        if text[i].isspace():
            while j < n and text[j].isspace():
                j += 1
        else:
            while j < n and unicodedata.combining(text[j]):
                j += 1
        spans.append((i, j))
        i = j
    return spans


def normalize_with_map(text: str) -> tuple[str, list[Span]]:
    """NFC + whitespace folded to one space; `spans[k]` is the original range of char `k`."""
    out: list[str] = []
    spans: list[Span] = []
    for start, end in _clusters(text):
        chunk = text[start:end]
        piece = " " if chunk[0].isspace() else unicodedata.normalize("NFC", chunk)
        out.append(piece)
        spans.extend([(start, end)] * len(piece))
    return "".join(out), spans


def _norm(text: str) -> str:
    return normalize_with_map(text)[0]


def unescape_quote(quote: str) -> str:
    """Undo the prompt's `& < >` escaping in one pass (not html.unescape): the model copies
    what it was shown."""
    table = {"&lt;": "<", "&gt;": ">", "&amp;": "&"}
    return re.sub(r"&(?:lt|gt|amp);", lambda m: table[m.group(0)], quote)


def find_quote(text: str, quote: str) -> Span | None:
    """First `[start, end)` in `text` whose normalized form equals the normalized quote."""
    needle = _norm(quote).strip()
    if len(needle) < MIN_QUOTE_CHARS or "\x00" in needle:
        return None
    haystack, spans = normalize_with_map(text)
    at = haystack.find(needle)
    if at < 0:
        return None
    start = spans[at][0]
    end = spans[at + len(needle) - 1][1]
    if _norm(text[start:end]).strip() != needle:
        return None
    return start, end
