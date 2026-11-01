"""T9.6b pure rules of generated questions (US-17 AC3, AC4)."""

import pytest

from core_api.domain.generated_questions import (
    MAX_EXISTING_ITEM_CHARS,
    MAX_EXISTING_ITEMS,
    MAX_EXISTING_TOTAL_CHARS,
    cap_existing,
    rubric_ideas,
)


@pytest.mark.parametrize(
    ("text", "ideas"),
    [
        ("Nêu ý chính. Dùng đúng thẻ.", ["Nêu ý chính.", "Dùng đúng thẻ."]),
        ("- Ý một\n- Ý hai\n3) Ý ba", ["Ý một", "Ý hai", "Ý ba"]),
        ("Một ý duy nhất không dấu chấm", ["Một ý duy nhất không dấu chấm"]),
    ],
)
def test_rubric_text_becomes_ideas(text: str, ideas: list[str]) -> None:
    # US-17 AC4. Red when: the model's rubric text cannot be graded point by point.
    assert rubric_ideas(text) == ideas


@pytest.mark.parametrize(
    "text", ["", "   \n ", "\n".join(f"Ý {n}" for n in range(9)), "Ý " + "d" * 400]
)
def test_a_rubric_that_cannot_be_graded_is_none(text: str) -> None:
    # US-17 AC4. Red when: an empty, a nine-idea or an over-long-idea rubric is accepted (it is
    # never cut: the overall would be judged on part of it).
    assert rubric_ideas(text) is None


def test_existing_prompts_are_bounded_deduplicated_and_cut() -> None:
    # US-17 AC3. Red when: the list, an item or the total grows without bound.
    many = [f"{n} " + "x" * 900 for n in range(500)]
    capped = cap_existing(["  ", "Câu A", "Câu A", *many])
    assert capped[0] == "Câu A" and capped.count("Câu A") == 1
    assert len(capped) <= MAX_EXISTING_ITEMS
    assert all(len(p) <= MAX_EXISTING_ITEM_CHARS for p in capped)
    assert sum(len(p) for p in capped) <= MAX_EXISTING_TOTAL_CHARS
