"""V3: contents pages recognised by their text and parsed by code, before the model is asked."""

from ai_service.pdf import OutlineEntry, PageText
from ai_service.tasks.syllabus import SyllabusPrompt, build_syllabus


def _no_ask(prompt: SyllabusPrompt) -> str:
    raise AssertionError("the model must not be asked")


def _pages(*texts: str) -> list[PageText]:
    return [PageText(text=t, needs_vision=False) for t in texts]


TOC = "\n".join(
    [
        "Mục lục",
        "Chương 1. Biến cố và xác suất . . . . . . . . . . . . 3",
        "1.1. Giải tích tổ hợp . . . . . . . . . . . . . . . 3",
        "1.2. Phép thử và biến cố . . . . . . . . . . . . . . 5",
        "Chương 2. Biến ngẫu nhiên . . . . . . . . . . . . . . 8",
        "2.1. Biến ngẫu nhiên rời rạc . . . . . . . . . . . . 8",
        "2.2. Biến ngẫu nhiên liên tục . . . . . . . . . . . . 10",
    ]
)


def _book() -> list[PageText]:
    body = ["Nội dung trang"] * 9
    return _pages("Bìa", TOC, *body)  # file page 3 prints "3": no offset


def test_contents_page_gives_chapters_and_sections_without_the_model() -> None:
    nodes = build_syllabus(11, [], _book(), _no_ask)
    assert {n.source for n in nodes} == {"toc_text"}
    chapters = [n for n in nodes if n.level == 0 and not n.excluded]
    assert [c.title for c in chapters] == [
        "Chương 1. Biến cố và xác suất",
        "Chương 2. Biến ngẫu nhiên",
    ]
    sections = [n.title for n in nodes if n.level == 1]
    assert sections[:2] == ["1.1. Giải tích tổ hợp", "1.2. Phép thử và biến cố"]
    assert nodes[0].excluded  # the cover before the first chapter


def test_a_part_is_not_a_chapter() -> None:
    toc = "Phần 1. Xác suất . . . . . . . . 3\n" + TOC.split("\n", 1)[1]
    nodes = build_syllabus(11, [], _pages("Bìa", toc, *["x"] * 9), _no_ask)
    assert not any(n.title.startswith("Phần 1") for n in nodes)


def test_bookmarks_named_after_files_are_not_a_syllabus() -> None:
    outline = [OutlineEntry(f"Chuong {i}.pdf", 0, i * 3) for i in range(4)]
    nodes = build_syllabus(11, outline, _book(), _no_ask)
    assert nodes[0].source == "toc_text"


def test_a_line_broken_at_every_lost_glyph_is_joined() -> None:
    fragments = "\n".join(
        [
            "Ch­¬ng 1. BiÕn ",
            "è ngÉu nhiªn . . . . . . . . . . . 3",
            "1.1. Gi¶i tÝ",
            "",
            "h tæ hîp . . . . . . . . . . . . . 3",
            "1.2. Php thö . . . . . . . . . . . . 5",
            "Ch­¬ng 2. Quy luËt . . . . . . . . . 8",
            "2.1. Mét . . . . . . . . . . . . . . 8",
        ]
    )
    nodes = build_syllabus(11, [], _pages("Bìa", fragments, *["x"] * 9), _no_ask)
    assert nodes[1].source == "toc_text"
    assert "1.1. Gi¶i tÝh tæ hîp" in [n.title for n in nodes]


def test_a_book_without_contents_still_falls_through() -> None:
    nodes = build_syllabus(11, [], _pages(*["Nội dung"] * 11), lambda p: '{"entries": []}')
    assert nodes[0].source == "chunk10"
