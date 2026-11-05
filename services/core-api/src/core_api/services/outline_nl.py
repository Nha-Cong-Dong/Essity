"""The common outline sentences, read by pattern before any model call (QA 05/11 Q25): "bỏ Bài
tập chương 3", "loại bỏ mục 1.2 khỏi đề cương", "bỏ phụ lục và chương 4", "đánh dấu chương 2 là
đã học". A target is a section number ("1.2", "chương 3") or a title, whole or in part; a
sentence that names no section, or a name that fits several, is not read here (the model is the
fallback)."""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from core_api.db.models import DocSection

_VERBS = r"(?:bỏ qua|loại bỏ|loại ra|loại|bỏ|xóa|xoá|ẩn)"
_LEAVE_OUT = re.compile(
    rf"^(?:hãy |giúp mình |làm ơn )?{_VERBS}\s+(?P<what>.+?)"
    r"(?:\s+(?:ra )?khỏi (?:đề cương|môn|danh sách))?$"
)
_MARK = re.compile(
    r"^đánh dấu\s+(?P<what>.+?)\s+(?:là |đã )(?:đã )?(?P<state>học xong|đã học|học rồi|xong)$"
)
_LEAD = re.compile(r"^(?:mục|chương|phần|bài|chapter|section)\s+")
_NUMBER = re.compile(r"^\d+(?:\.\d+)*$")
_SPLIT = re.compile(r"\s*(?:,|;|\bvà\b|\bvới\b)\s*")


@dataclass(frozen=True)
class OutlineIntent:
    kind: str  # section_exclude | section_mark
    sections: list[DocSection]
    studied: bool = True


def fold(text: str) -> str:
    """Case, accents and spacing out of the way: "Bài tập" matches "bai  tap"."""
    nfd = unicodedata.normalize("NFD", unicodedata.normalize("NFC", text).casefold())
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn").replace("đ", "d")
    return " ".join(stripped.split())


def _resolve(sections: Sequence[DocSection], target: str) -> DocSection | None:
    """The one section `target` names, or None (nothing, or several)."""
    want = fold(target).strip(" .\"“”'")
    if not want:
        return None
    titles = [(s, fold(s.title)) for s in sections]
    for candidate in dict.fromkeys([want, _LEAD.sub("", want)]):
        if not candidate:
            continue
        exact = [s for s, t in titles if t == candidate]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            return None
        # a bare number is the start of a title ("1.2", "chuong 3: ..."), not a part of one
        bare = _NUMBER.match(candidate) is not None
        head = rf"^(?:(?:chuong|phan|muc|bai|chapter|section)\s*)?{re.escape(candidate)}(?!\d|\.\d)"
        inside = rf"(?<![\w.]){re.escape(candidate)}(?!\d|\.\d)(?!\w)"
        for pattern in [head] if bare else [head, inside]:
            found = [s for s, t in titles if re.search(pattern, t)]
            if len(found) == 1:
                return found[0]
            if len(found) > 1:
                return None
    return None


def read_outline_sentence(sections: Sequence[DocSection], text: str) -> OutlineIntent | None:
    line = " ".join(unicodedata.normalize("NFC", text).casefold().split()).rstrip(".!? ")
    if (m := _LEAVE_OUT.match(line)) is not None:
        kind = "section_exclude"
    elif (m := _MARK.match(line)) is not None:
        kind = "section_mark"
    else:
        return None
    parts = [p for p in _SPLIT.split(m.group("what")) if p.strip()]
    if not parts:
        return None
    found: list[DocSection] = []
    for part in parts:
        section = _resolve(sections, part)
        if section is None:
            # "bỏ chương 3 và chương 4" splits fine; a title with "và" in it is tried whole
            whole = _resolve(sections, m.group("what"))
            if whole is None or len(parts) == 1:
                return None
            return OutlineIntent(kind, [whole])
        if section not in found:
            found.append(section)
    return OutlineIntent(kind, found)
