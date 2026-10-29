"""anchor_check (T4.15, US-02b AC3): a quote counts only if the code finds it in the page text."""

import random
import unicodedata

from ai_service.domain.anchor_check import (
    MIN_QUOTE_CHARS,
    find_quote,
    normalize_with_map,
    unescape_quote,
)

PAGE = "Mitochondria are the site of cellular respiration in eukaryotic cells."


def test_exact_quote_found_AC3() -> None:
    quote = "site of cellular respiration"
    start, end = find_quote(PAGE, quote) or (-1, -1)
    assert PAGE[start:end] == quote


def test_fabricated_quote_not_found_AC3() -> None:
    assert find_quote(PAGE, "chloroplasts perform photosynthesis in leaves") is None


def test_offsets_refer_to_original_text_AC3() -> None:
    page = unicodedata.normalize(
        "NFD", "Phản ứng\n\n  tổng hợp   ATP diễn ra ở ty thể, rất hiệu quả."
    )
    quote = unicodedata.normalize("NFC", "Phản ứng tổng hợp ATP diễn ra ở ty thể")
    start, end = find_quote(page, quote) or (-1, -1)
    assert start == 0
    got = normalize_with_map(page[start:end])[0]
    assert got == quote
    assert page[end:].startswith(unicodedata.normalize("NFD", ", rất"))


def test_nfd_quote_matches_nfc_page_AC3() -> None:
    page = unicodedata.normalize("NFC", "Điều kiện cần và đủ của hàm số đồng biến")
    quote = unicodedata.normalize("NFD", "kiện cần và đủ của hàm số")
    start, end = find_quote(page, quote) or (-1, -1)
    assert page[start:end] == "kiện cần và đủ của hàm số"


def test_empty_or_short_quote_dropped() -> None:
    assert find_quote(PAGE, "") is None
    assert find_quote(PAGE, "   \n ") is None
    assert find_quote(PAGE, "a" * (MIN_QUOTE_CHARS - 1)) is None


def test_short_boundary() -> None:
    page = "x" * 3 + "abcdefghijklmno" + "y"
    assert find_quote(page, "abcdefghijklmno") == (3, 18)
    assert find_quote(page, "abcdefghijklmn") is None


def test_case_sensitive() -> None:
    assert find_quote(PAGE, "SITE OF CELLULAR RESPIRATION") is None


def test_first_match_taken() -> None:
    page = "the same long sentence here. the same long sentence here."
    assert find_quote(page, "the same long sentence here") == (0, 27)


def test_non_bmp_offsets_are_code_points() -> None:
    page = "\U0001f600 mở đầu về năng lượng tế bào \U0001f600 kết thúc"
    start, end = find_quote(page, "về năng lượng tế bào") or (-1, -1)
    assert page[start:end] == "về năng lượng tế bào"


def test_unescape_quote_one_pass() -> None:
    assert unescape_quote("a &lt;b&gt; &amp;amp; c") == "a <b> &amp; c"
    assert unescape_quote("x &amp;lt; y") == "x &lt; y"


def test_mapping_invariant_random_AC3() -> None:
    rng = random.Random(1234)
    alphabet = ["a", "b", " ", "\n", "\t", "ế", "ế", "ê", "\U0001f600", "é", "é", "."]
    for _ in range(300):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(20, 80)))
        norm, spans = normalize_with_map(text)
        assert len(norm) == len(spans)
        i = rng.randrange(len(norm))
        j = min(len(norm), i + rng.randint(15, 30))
        quote = norm[i:j]
        found = find_quote(text, quote)
        if quote.strip() and len(quote.strip()) >= MIN_QUOTE_CHARS:
            assert found is not None
            s, e = found
            assert normalize_with_map(text[s:e])[0].strip() == quote.strip()
