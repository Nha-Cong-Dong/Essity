"""TCVN3 (.Vn fonts) text is converted to Unicode; other text is left alone."""

from ai_service.pdf.legacy_vn import fix_tcvn3, looks_tcvn3


def test_tcvn3_text_becomes_unicode() -> None:
    text = "Ch­¬ng 1. BiÕn ngÉu nhiªn vµ ®Þnh lý x¸c suÊt"
    assert looks_tcvn3(text)
    out = fix_tcvn3(text)
    assert out.startswith("Chương 1. Biến ngẫu nhiên và")
    assert out.endswith("định lý xác suất")


def test_plain_vietnamese_and_french_are_untouched() -> None:
    for text in (
        "Chương 1. Biến ngẫu nhiên và xác suất " * 5,
        "Un été très élégant à Paris, déjà vu " * 5,
    ):
        assert not looks_tcvn3(text)
        assert fix_tcvn3(text) == text


def test_lost_glyphs_come_back_as_c_e_acute_and_u_dot() -> None:
    # "các định lý" with the "c" as a lone CR, then "phép" (U+001C) and "mục" (U+001D, CR).
    text = "\r¸\r ®Þnh lý, ph\x1cp, M\x1d\r, tÝ\rh, x¸\r" * 2 + "\r\n"
    out = fix_tcvn3(text)
    assert "các định lý, phép, Mục, tích, xác" in out
    assert out.endswith("\r\n")


def test_lost_capital_u_horn_comes_back() -> None:
    # Seen in a real textbook: the capital U-horn has no Unicode mapping and is U+0019, so
    # "Ước lượng" and "Ưu điểm" lost their first letter downstream.
    text = "Ch­¬ng 4. \x19í\r l­îng tham sè. \x19u ®iÓm, ph­¬ng ph¸p\r\n" * 6
    out = fix_tcvn3(text)
    assert "Chương 4. Ước lượng tham số. Ưu điểm" in out
    assert "\x19" not in out


def test_capital_y_after_a_section_number_is_restored() -> None:
    # Seen in a real textbook: the capital Y-acute is printed with the lowercase glyph (0xFD), so
    # "3.4. Ý nghĩa" reads "3.4. ý nghĩa". Only a title right after a section number is capital.
    text = "Ch­¬ng 3. Ch\xadng\r\n3.4. \xfd ngh\xdca thèng kª\r\nvà ý kiến, \xfd tưởng\r\n" * 4
    out = fix_tcvn3(text)
    assert "3.4. Ý nghĩa" in out
    assert "và ý kiến" in out
