"""QA2 N4: "bỏ mục 2" on a real XSTK outline ("Chương 2. ..." chapters, "1.2." sub-sections)."""

from types import SimpleNamespace
from typing import Any, cast

from core_api.services.outline_nl import read_outline_sentence

TITLES = [
    "Chương 1. Biến cố ngẫu nhiên và xác suất",
    "1.1. Giải tích tổ hợp",
    "1.2. Biến cố",
    "Chương 2. Biến ngẫu nhiên",
    "2.1. Biến ngẫu nhiên rời rạc",
]


def _sections(titles: list[str]) -> list[Any]:
    return cast(list[Any], [SimpleNamespace(title=t) for t in titles])


def test_bare_section_two_fits_chapter_and_subsection_so_it_is_not_guessed() -> None:
    assert read_outline_sentence(_sections(TITLES), "bỏ mục 2") is None


def test_all_caps_chapter_title_also_asks() -> None:
    titles = ["CHƯƠNG 1 XÁC SUẤT", "1.2. Biến cố", "CHƯƠNG 2 BIẾN NGẪU NHIÊN"]
    assert read_outline_sentence(_sections(titles), "bỏ mục 2") is None


def test_explicit_chapter_two_still_reads() -> None:
    secs = _sections(TITLES)
    got = read_outline_sentence(secs, "bỏ chương 2")
    assert got is not None and got.sections == [secs[3]]
