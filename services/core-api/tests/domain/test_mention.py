"""`@name` mentions resolved without AI (T7.6; US-02 AC3 scope forms, AC4 clear errors). Pure."""

import uuid

import pytest

from core_api.domain.mention import (
    DocInfo,
    ExplicitMention,
    MentionError,
    ResolvedMention,
    SectionInfo,
    fold,
    resolve_mentions,
)


def uid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


NET = DocInfo(uid(1), "Mạng máy tính", "pdf", 200)
DB = DocInfo(uid(2), "CSDL", "pptx", 60)
DOCS = [NET, DB]


def sec(n: int, title: str, parent: int | None = None, ord_: int = 0, **pages: int) -> SectionInfo:
    return SectionInfo(uid(n), uid(parent) if parent else None, ord_, title, **pages)


NET_SECTIONS = [
    sec(10, "Chương 1. Giới thiệu", ord_=0, first_page=5, last_page=30),
    sec(11, "Chương 3. Tầng mạng", ord_=2, first_page=40, last_page=55),
    sec(12, "3.1 Định tuyến", parent=11, ord_=0, first_page=41, last_page=45),
    sec(13, "3.2 Địa chỉ IP", parent=11, ord_=1),
]
SECTIONS = {NET.id: NET_SECTIONS}


def run(text: str, docs: list[DocInfo] = DOCS, **kw: object) -> list[ResolvedMention]:
    return resolve_mentions(text, docs, SECTIONS, **kw)  # pyright: ignore[reportArgumentType]


def error(text: str, docs: list[DocInfo] = DOCS) -> MentionError:
    with pytest.raises(MentionError) as caught:
        run(text, docs)
    return caught.value


def test_whole_document_when_no_scope() -> None:
    assert run("Hôm nay học @Mạng máy tính.") == [ResolvedMention(0, NET.id, None, None, None)]


def test_scope_chapter() -> None:
    # Red when: "chương N" is not matched by the number the title starts with (AC3).
    assert run("@Mạng máy tính chương 3") == [ResolvedMention(0, NET.id, uid(11), 40, 55)]


def test_scope_chapter_english_and_list() -> None:
    got = run("@Mạng máy tính chapter 1 và 3")
    assert [(m.section_id, m.index) for m in got] == [(uid(10), 0), (uid(11), 1)]


def test_scope_section_path() -> None:
    assert run("@Mạng máy tính mục 3.1") == [ResolvedMention(0, NET.id, uid(12), 41, 45)]
    # A section with no page positions keeps only its id.
    assert run("@Mạng máy tính mục 3.2") == [ResolvedMention(0, NET.id, uid(13), None, None)]


def test_scope_pages_range() -> None:
    assert run("@Mạng máy tính tr. 40–55") == [ResolvedMention(0, NET.id, None, 40, 55)]
    assert run("@Mạng máy tính trang 7") == [ResolvedMention(0, NET.id, None, 7, 7)]
    assert run("@Mạng máy tính p. 3-4, 9") == [
        ResolvedMention(0, NET.id, None, 3, 4),
        ResolvedMention(1, NET.id, None, 9, 9),
    ]


def test_scope_slide_range() -> None:
    assert run("@CSDL slide 4-9") == [ResolvedMention(0, DB.id, None, 4, 9)]


def test_two_documents_one_sentence() -> None:
    # Red when: the scope of the first mention swallows the second mention.
    got = run("Học @Mạng máy tính chương 3 và @CSDL slide 4")
    assert [(m.document_id, m.section_id, m.first_page) for m in got] == [
        (NET.id, uid(11), 40),
        (DB.id, None, 4),
    ]


def test_scope_ends_at_line_break_and_semicolon() -> None:
    got = run("@Mạng máy tính chương 1; xong\n@CSDL")
    assert [m.document_id for m in got] == [NET.id, DB.id]


def test_free_text_after_the_name_is_not_a_scope() -> None:
    assert run("@CSDL hôm nay khá khó") == [ResolvedMention(0, DB.id, None, None, None)]


def test_an_email_address_is_not_a_mention() -> None:
    assert run("gửi cho a@CSDL.com") == []


def test_same_input_same_output_across_runs() -> None:
    text = "@Mạng máy tính chương 3 và @CSDL slide 2-3"
    assert run(text) == run(text) == run(text, docs=list(reversed(DOCS)))


@pytest.mark.parametrize("text", ["@mang may tinh", "@MẠNG  MÁY   TÍNH", "@mạng máy tính"])
def test_accent_and_case_insensitive_name(text: str) -> None:
    assert [m.document_id for m in run(text)] == [NET.id]


def test_the_longest_name_wins() -> None:
    short = DocInfo(uid(3), "Mạng", "pdf", 10)
    assert run("@Mạng máy tính", [short, NET])[0].document_id == NET.id
    assert run("@Mạng", [short, NET])[0].document_id == short.id


def test_a_name_must_end_at_a_word_boundary() -> None:
    assert error("@CSDLx").code == "mention_not_found"


# --- Errors name the part (AC4) -----------------------------------------------------------------


def test_unknown_name_names_the_part() -> None:
    err = error("@Vật lý chương 1")
    assert (err.code, err.mention, err.part) == ("mention_not_found", 0, "vat")


def test_unknown_chapter_names_part() -> None:
    # Red when: an unknown chapter resolves to something anyway (no guessing).
    err = error("ok @Mạng máy tính chương 9")
    assert (err.code, err.mention, err.part) == ("scope_not_found", 0, "chuong 9")


def test_page_outside_page_count() -> None:
    err = error("@Mạng máy tính tr. 190-250")
    assert (err.code, err.part) == ("scope_out_of_range", "tr. 190-250")
    assert error("@Mạng máy tính trang 0").code == "scope_out_of_range"
    assert error("@Mạng máy tính tr. 9-3").code == "scope_out_of_range"


def test_slide_on_a_non_pptx_document() -> None:
    assert error("@Mạng máy tính slide 3").code == "scope_unsupported"


def test_ambiguous_name_lists_candidates() -> None:
    twin = DocInfo(uid(4), "csdl", "pdf", 10)
    err = error("@CSDL", [DB, twin])
    assert err.code == "mention_ambiguous"
    assert err.candidates == (uid(2), uid(4))


def test_second_mention_error_carries_its_index() -> None:
    assert error("@CSDL slide 2 và @Lạ").mention == 1


# --- Titles without numbers, and ambiguity -------------------------------------------------------


def test_unnumbered_titles_count_by_position() -> None:
    doc = DocInfo(uid(5), "Sách", "pdf", 100)
    sections = {
        doc.id: [sec(20, "Mở đầu", ord_=0), sec(21, "Mạng", ord_=1), sec(22, "Lớp", parent=21)]
    }
    got = resolve_mentions("@Sách chương 2; @Sách mục 2.1", [doc], sections)
    assert [m.section_id for m in got] == [uid(21), uid(22)]


def test_two_chapters_with_the_same_number_are_ambiguous() -> None:
    doc = DocInfo(uid(5), "Sách", "pdf", 100)
    sections = {doc.id: [sec(20, "Chương 1 A"), sec(21, "Chương 1 B", ord_=1)]}
    with pytest.raises(MentionError) as caught:
        resolve_mentions("@Sách chương 1", [doc], sections)
    assert caught.value.code == "scope_ambiguous"
    assert caught.value.candidates == (uid(20), uid(21))


def test_pages_range_uses_page_labels_when_present() -> None:
    # Red when: a printed number is taken for a file position (P5).
    doc = DocInfo(uid(6), "Giáo trình", "pdf", 6, page_labels=["i", "ii", "1", "2", "3", "4"])
    got = resolve_mentions("@Giáo trình tr. 2-3", [doc], {})
    assert got == [ResolvedMention(0, doc.id, None, 4, 5)]
    with pytest.raises(MentionError) as caught:
        resolve_mentions("@Giáo trình tr. 9", [doc], {})
    assert caught.value.code == "scope_out_of_range"


def test_without_page_labels_the_number_is_the_file_position() -> None:
    assert run("@Mạng máy tính tr. 200")[0].first_page == 200


# --- Explicit document ids (P3) -------------------------------------------------------------------


def test_mention_by_document_id_resolves_despite_ambiguous_name() -> None:
    twin = DocInfo(uid(4), "csdl", "pptx", 10)
    text = "học @CSDL slide 2"
    got = resolve_mentions(text, [DB, twin], {}, [ExplicitMention(twin.id, 4, 9)])
    assert got == [ResolvedMention(0, twin.id, None, 2, 2)]


def test_explicit_mention_with_an_unknown_document_is_not_found() -> None:
    err = pytest.raises(
        MentionError,
        resolve_mentions,
        "@CSDL",
        DOCS,
        {},
        [ExplicitMention(uid(99), 0, 5)],
    )
    assert err.value.code == "mention_not_found"


def test_fold() -> None:
    assert fold("  Đường  Đi ") == "duong di"
    assert fold("A–B") == "a-b"
