"""Pure rules for generated practice questions (T9.6b, US-17): no database, no AI.

The neutral lines are what the screen shows; the backend owns the words (US-17 §6, AC8).
"""

import re
from collections.abc import Iterable

# pg_trgm `similarity()` at or above it makes a stored question a near-duplicate (US-17 §9 #1).
# Provisional, like the Jaccard 3-gram threshold in ai-service: to be settled by the T9.7 eval.
TRIGRAM_THRESHOLD = 0.7

# What core sends as `existing_prompts` (ai-service holds no list length of its own beyond 200,
# and no per-item length): the newest first, each cut, all within a total, so a big bank cannot
# push the request past ai-service's body limit.
MAX_EXISTING_ITEMS = 100
MAX_EXISTING_ITEM_CHARS = 300
MAX_EXISTING_TOTAL_CHARS = 30_000

# The rubric ideas core-api can grade against (practice_grading: at most 8, each at most 400).
MAX_RUBRIC_IDEAS = 8
MAX_IDEA_CHARS = 400

CANDIDATES_PER_CLICK = 5
# A `running` row older than this is a crashed request, not a click in flight.
RUNNING_STALE_SECONDS = 60

MSG_EMPTY = "Chưa có câu sinh thêm nào đủ tốt. Thử lại sau khi học thêm thẻ."
MSG_PENDING_AI = "Hiện chưa sinh được câu mới. Thử lại sau."
MSG_NO_CARDS = "Chưa có thẻ đã học để sinh câu. Học thêm thẻ rồi thử lại."
MSG_RUNNING = "Đang sinh câu, chờ một chút."
MSG_FAILED = "Chưa sinh được câu lần này. Thử lại sau."

_SPLIT = re.compile(r"\n+|(?<=[.!?;])\s+")
_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s*")


def rubric_ideas(rubric: str) -> list[str] | None:
    """The model's rubric text as a list of ideas, or None when it cannot be graded against.
    Split on lines and sentence ends, bullets stripped; never cut: an idea longer than the
    grader accepts, or more than eight, makes the candidate unusable."""
    ideas = [_BULLET.sub("", part).strip() for part in _SPLIT.split(rubric)]
    ideas = [idea for idea in ideas if idea]
    if not ideas or len(ideas) > MAX_RUBRIC_IDEAS or any(len(i) > MAX_IDEA_CHARS for i in ideas):
        return None
    return ideas


def cap_existing(prompts: Iterable[str]) -> list[str]:
    """`prompts` newest first -> what is sent: blanks and repeats dropped, each cut, the list and
    its total bounded."""
    kept: list[str] = []
    seen: set[str] = set()
    total = 0
    for prompt in prompts:
        text = prompt.strip()[:MAX_EXISTING_ITEM_CHARS]
        if not text or text in seen:
            continue
        if len(kept) >= MAX_EXISTING_ITEMS or total + len(text) > MAX_EXISTING_TOTAL_CHARS:
            break
        seen.add(text)
        kept.append(text)
        total += len(text)
    return kept
