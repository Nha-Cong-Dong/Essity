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


def test_sections_sharing_a_page_all_stay_in_the_outline() -> None:
    """Short sections share a page: 1.1.2 and 1.1.3 start on page 4. None may vanish, or the
    learner's next step jumps from 1.1.1 to 1.1.3."""
    toc = "\n".join(
        [
            "Mục lục",
            "Chương 1. Giải tích tổ hợp . . . . . . . . . . . . 3",
            "1.1.1. Quy tắc cộng . . . . . . . . . . . . . . . 3",
            "1.1.2. Quy tắc nhân . . . . . . . . . . . . . . . 4",
            "1.1.3. Hoán vị . . . . . . . . . . . . . . . . . . 4",
            "1.1.4. Chỉnh hợp . . . . . . . . . . . . . . . . . 6",
            "1.1.5. Tổ hợp . . . . . . . . . . . . . . . . . . . 6",
            "1.1.6. Nhị thức . . . . . . . . . . . . . . . . . . 6",
            "1.1.7. Bài tập . . . . . . . . . . . . . . . . . . 8",
        ]
    )
    nodes = build_syllabus(10, [], _pages("Bìa", toc, *["x"] * 8), _no_ask)
    assert {n.source for n in nodes} == {"toc_text"}
    text = " | ".join(n.title for n in nodes)
    for number in ("1.1.1", "1.1.2", "1.1.3", "1.1.4", "1.1.5", "1.1.6", "1.1.7"):
        assert number in text, number
    leaves = [n for n in nodes if not any(m.ord == n.ord + 1 and m.level > n.level for m in nodes)]
    assert sum(n.weight for n in leaves) == 10  # still tiles every page once
