"""`@name` mentions, edge cases the tester added (T7.6; US-02 AC3 scope forms, AC4 clear errors,
no guessing). Pure; each one fails under a mutation of `domain/mention.py` the first suite let
through."""

import uuid

import pytest

from core_api.domain.mention import (
    MAX_MENTIONS,
    DocInfo,
    ExplicitMention,
    MentionError,
    ResolvedMention,
    SectionInfo,
    resolve_mentions,
)


def uid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def sec(n: int, title: str, parent: int | None = None, ord_: int = 0) -> SectionInfo:
    return SectionInfo(uid(n), uid(parent) if parent else None, ord_, title)


SLIDES = DocInfo(uid(2), "CSDL", "pptx", 60)
BOOK = DocInfo(uid(5), "Sách", "pdf", 100)


def code_of(text: str, docs: list[DocInfo], sections: dict[uuid.UUID, list[SectionInfo]]) -> str:
    with pytest.raises(MentionError) as caught:
        resolve_mentions(text, docs, sections)
    return caught.value.code


def test_more_than_max_mentions_is_refused() -> None:
    # Red when: the mention ceiling is not enforced (P4; one description fans out unbounded).
    ok = "; ".join(f"@CSDL slide {i}" for i in range(1, MAX_MENTIONS + 1))
    assert len(resolve_mentions(ok, [SLIDES], {})) == MAX_MENTIONS
    over = ok + f"; @CSDL slide {MAX_MENTIONS + 1}"
    assert code_of(over, [SLIDES], {}) == "too_many_mentions"


def test_a_scope_list_counts_toward_the_ceiling() -> None:
    # Red when: "slide 1, 2, ..." in one mention escapes the ceiling.
    items = ", ".join(str(i) for i in range(1, MAX_MENTIONS + 2))
    assert code_of(f"@CSDL slide {items}", [SLIDES], {}) == "too_many_mentions"


def test_explicit_mention_running_past_its_segment_is_not_found() -> None:
    # Red when: an explicit (document_id, start, end) whose end crosses into the next mention,
    # or ends before it starts, is taken as given.
    text = "@CSDL slide 2; @Sách"
    for end in (len(text), 0):
        with pytest.raises(MentionError) as caught:
            resolve_mentions(text, [SLIDES, BOOK], {}, [ExplicitMention(SLIDES.id, 0, end)])
        assert caught.value.code == "mention_not_found"


def test_chapter_number_matches_top_level_sections_only() -> None:
    # Red when: "chương 3" resolves to a nested section that happens to be titled "3 ...".
    sections = {BOOK.id: [sec(20, "Chương 2. Mạng", ord_=0), sec(21, "3 Phụ lục", parent=20)]}
    assert code_of("@Sách chương 3", [BOOK], sections) == "scope_not_found"
    got = resolve_mentions("@Sách mục 3", [BOOK], sections)
    assert [m.section_id for m in got] == [uid(21)]


def test_chapter_with_a_dotted_number_is_not_found_in_an_unnumbered_tree() -> None:
    # Red when: "chương 2.1" silently walks into a subsection when titles carry no numbers.
    sections = {BOOK.id: [sec(20, "Mở đầu", ord_=0), sec(21, "Mạng", ord_=1), sec(22, "Lớp", 21)]}
    assert code_of("@Sách chương 2.1", [BOOK], sections) == "scope_not_found"
    assert resolve_mentions("@Sách mục 2.1", [BOOK], sections)[0].section_id == uid(22)


def test_page_label_must_match_whole_not_by_prefix() -> None:
    # Red when: printed page 1 is found at the label "10" (prefix match), a silent wrong page.
    doc = DocInfo(uid(6), "Giáo trình", "pdf", 3, page_labels=["10", "1", "2"])
    assert resolve_mentions("@Giáo trình tr. 1", [doc], {}) == [
        ResolvedMention(0, doc.id, None, 2, 2)
    ]


def test_out_of_order_sections_resolve_by_ord_not_by_input_order() -> None:
    # Red when: position counting follows the order rows arrive, not (ord, id).
    sections = {BOOK.id: [sec(30, "Hai", ord_=1), sec(31, "Một", ord_=0)]}
    assert resolve_mentions("@Sách chương 1", [BOOK], sections)[0].section_id == uid(31)
