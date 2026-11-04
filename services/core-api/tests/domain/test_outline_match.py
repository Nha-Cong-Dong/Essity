"""Matching an outline read again to the one the learner has worked on (OUTLINE-FIX3)."""

from core_api.domain.outline import match_titles, title_key


def test_title_key_splits_number_and_folds_words() -> None:
    assert title_key("3.4. Ý nghĩa thống kê") == ("3.4", "y nghia thong ke")
    assert title_key("Chương 4. Ước lượng") == ("chuong4", "uoc luong")
    assert title_key("Lời nói đầu") == ("", "loi noi dau")


def test_equal_number_and_title_match() -> None:
    old = ["1. Xác suất", "1.1. Biến cố"]
    assert match_titles(old, ["1.1. Biến cố", "1. Xác suất"]) == {0: 1, 1: 0}


def test_a_fixed_title_keeps_its_number_match() -> None:
    old = ["2.3.1. Quy luật chuẩn N(a,σ2", "2.3.2. Quy luật khi bình phương-χ"]
    new = ["2.3.1. Quy luật chuẩn N(a,σ2)", "2.3.2. Quy luật khi bình phương-χ2"]
    assert match_titles(old, new) == {0: 0, 1: 1}


def test_a_garbage_section_matches_nothing() -> None:
    old = ["1. Xác suất", ")"]
    assert match_titles(old, ["1. Xác suất", "2.3.1. Quy luật chuẩn"]) == {0: 0}


def test_accent_fix_matches_by_words_without_number() -> None:
    assert match_titles(["Loi noi dau", "Phu luc"], ["Lời nói đầu"]) == {0: 0}


def test_a_number_held_twice_does_not_match_by_number_alone() -> None:
    old = ["1.1. A", "1.1. B"]
    assert match_titles(old, ["1.1. C"]) == {}


def test_duplicate_titles_pair_in_order() -> None:
    old = ["Bài tập", "Bài tập"]
    assert match_titles(old, ["Bài tập", "Bài tập"]) == {0: 0, 1: 1}
