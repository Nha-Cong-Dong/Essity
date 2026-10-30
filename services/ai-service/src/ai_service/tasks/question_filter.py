"""Code filter for generated practice questions (T9.6a, US-17 AC2, AC3).

Pure and independent of the model, so prompt injection through card text cannot move it:
  - a candidate may cite only studied cards (labels the caller handed out);
  - a candidate too close to the sample, to an existing question or to a kept candidate is
    dropped, by Jaccard over word 3-grams. The `pg_trgm` check on stored questions is DB-side
    (T9.6b).
Reasons are rule names only: no question or card text reaches a reason, a log or an exception.
"""

import re
from collections.abc import Iterable, Sequence

# Provisional (US-17 §9 #1): to be settled with the T9.7 eval. A pair at or above it is a
# near-duplicate.
SIMILARITY_THRESHOLD = 0.6
NGRAM_WORDS = 3

REASON_UNSTUDIED_CARD = "unstudied_card"
REASON_NO_CARD = "no_card"
REASON_NEAR_DUPLICATE = "near_duplicate"

_WORD = re.compile(r"\w+")


def ngrams(text: str) -> frozenset[tuple[str, ...]]:
    """Word 3-grams, case-folded. Fewer than three words: the whole text is one gram, so two
    identical short questions still match."""
    words = _WORD.findall(text.casefold())
    if not words:
        return frozenset()
    if len(words) < NGRAM_WORDS:
        return frozenset({tuple(words)})
    return frozenset(tuple(words[i : i + NGRAM_WORDS]) for i in range(len(words) - NGRAM_WORDS + 1))


def jaccard(a: str, b: str) -> float:
    grams_a, grams_b = ngrams(a), ngrams(b)
    if not grams_a or not grams_b:
        return 0.0
    return len(grams_a & grams_b) / len(grams_a | grams_b)


def is_near_duplicate(
    text: str, others: Iterable[str], threshold: float = SIMILARITY_THRESHOLD
) -> bool:
    return any(jaccard(text, other) >= threshold for other in others)


def cited_cards_reason(cited: Sequence[str], studied: frozenset[str]) -> str | None:
    """None when the candidate cites at least one card and only studied ones."""
    if not cited:
        return REASON_NO_CARD
    if any(label not in studied for label in cited):
        return REASON_UNSTUDIED_CARD
    return None
