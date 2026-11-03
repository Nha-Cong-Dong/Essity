"""Sections left out of the exam outline by default (T7.2b, US-13): the pages before the first
heading and top-level sections that are not content (cover, preface, contents, index...). The
learner can bring one back ("Đưa lại"); core-api stores the flag as `doc_section.excluded`.

Matching is on the whole title, so a chapter that merely starts with such a word is kept.
`Phụ lục` / `Appendix` are NOT excluded: an appendix is often examined (worked tables, proofs).
Nothing here logs a title.
"""

import re
import unicodedata

# Vietnamese for the leaf that holds the pages before the first heading.
FRONT_MATTER_TITLE = "Phần đầu sách"

_TERMS = (
    r"(?:front\s+|back\s+)?cover(?:\s+page)?|title\s+page|copyright(?:\s+page)?|dedication"
    r"|(?:preface|foreword)(?:\s+to\s+.*)?|acknowledge?ments?|about\s+the\s+authors?"
    r"|(?:(?:brief|detailed|short)\s+)?(?:table\s+of\s+)?contents"
    r"|(?:subject\s+|name\s+|author\s+)?index|bibliography|references|works\s+cited"
    r"|loi\s+noi\s+dau|loi\s+gioi\s+thieu|loi\s+tua|loi\s+cam\s+on|loi\s+tri\s+an"
    r"|muc\s+luc|tai\s+lieu\s+tham\s+khao|danh\s+muc\s+tai\s+lieu(?:\s+tham\s+khao)?"
    r"|chi\s+muc|bia(?:\s+sach)?|trang\s+bia|trang\s+phu\s+bia"
)
_NON_CONTENT = re.compile(rf"(?:{_TERMS})", re.I)
# A number, roman numeral or "Part"-less bullet in front of the name ("1. Preface", "iv Index").
_LEAD = re.compile(r"^\s*(?:\d+|[ivxlc]+)\s*[.):\-]?\s+", re.I)


def _plain(title: str) -> str:
    folded = unicodedata.normalize("NFD", title.replace("đ", "d").replace("Đ", "D"))
    text = "".join(c for c in folded if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip(" .:-–—\t")


def is_non_content_title(title: str) -> bool:
    """Whether a top-level section title names cover, preface, contents, index, bibliography
    or the like, in English or Vietnamese (accents optional)."""
    text = _plain(title)
    candidates = {text, _LEAD.sub("", text)}
    return any(_NON_CONTENT.fullmatch(c) for c in candidates if c)
