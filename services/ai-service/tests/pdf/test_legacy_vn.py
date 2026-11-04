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
