"""T7.2b: which top-level titles are left out of the outline by default."""

import pytest

from ai_service.tasks.outline_exclusion import is_non_content_title


@pytest.mark.parametrize(
    "title",
    [
        "Cover", "Front Cover", "Title page", "Copyright", "Preface",
        "Preface to the Second Edition",
        "FOREWORD", "Contents", "Table of Contents", "Brief Contents", "Acknowledgements",
        "Acknowledgments", "About the Authors", "Index", "Subject Index", "Bibliography",
        "References", "Lời nói đầu", "Loi noi dau", "Lời giới thiệu", "Mục lục",
        "MỤC LỤC", "Tài liệu tham khảo", "Danh mục tài liệu tham khảo", "Chỉ mục", "Trang bìa",
        "Lời cảm ơn", "1. Preface", "iv Index", "Contents:", "Appendix A", "Phụ lục A", "Phụ lục",
    ],
)  # fmt: skip
def test_non_content_titles_are_recognised(title: str) -> None:
    assert is_non_content_title(title)


@pytest.mark.parametrize(
    "title",
    [
        "Chapter 1", "Introduction", "Index numbers", "References and citation styles",
        "Glossary", "Chương 1: Mục lục hóa", "Cover letters",
        "Contents of a stomach", "", "Bìa cứng",
    ],
)  # fmt: skip
def test_content_titles_are_kept(title: str) -> None:
    assert not is_non_content_title(title)
