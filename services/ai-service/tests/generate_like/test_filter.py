"""T9.6a: code filter (US-17 AC2, AC3)."""

from ai_service.tasks.question_filter import (
    SIMILARITY_THRESHOLD,
    cited_cards_reason,
    is_near_duplicate,
    jaccard,
)

BASE = "one two three four five"  # 3 grams


def test_threshold_is_provisional_default() -> None:  # US-17 AC3
    assert SIMILARITY_THRESHOLD == 0.6


def test_jaccard_identical_and_disjoint() -> None:  # US-17 AC3
    assert jaccard("Alpha beta gamma delta", "alpha  BETA gamma delta") == 1.0
    assert jaccard("a b c d", "e f g h") == 0.0


def test_short_identical_texts_match() -> None:  # US-17 AC3
    assert jaccard("what is ATP", "What is atp") == 1.0
    assert jaccard("", "anything here now") == 0.0


def test_boundary_at_threshold_is_a_duplicate() -> None:  # US-17 AC3
    exactly = BASE + " six seven"  # 5 grams, shares 3: 3/5
    assert jaccard(BASE, exactly) == 0.6
    assert is_near_duplicate(BASE, [exactly])


def test_just_below_threshold_is_kept() -> None:  # US-17 AC3
    below = BASE + " six seven eight"  # 6 grams, shares 3: 3/6
    assert jaccard(BASE, below) == 0.5
    assert not is_near_duplicate(BASE, [below])


def test_cited_cards_rules() -> None:  # US-17 AC2
    studied = frozenset({"C1", "C2"})
    assert cited_cards_reason(["C1", "C2"], studied) is None
    assert cited_cards_reason(["C1", "C9"], studied) == "unstudied_card"
    assert cited_cards_reason([], studied) == "no_card"
