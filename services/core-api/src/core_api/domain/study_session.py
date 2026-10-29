"""Rules of a study session that need no database (US-02, T4.12)."""

import datetime
import uuid
from collections.abc import Iterable

# How far back a session may be logged: "ghi bù" for a day studied up to a year ago (Q14).
LATE_LOG_DAYS = 366

# POST /sessions answers within this, reading files and calling ai-service together. The chain
# shrinks downstream: web 6 s > core-api 5 s > ai-service 4 s (CONVENTIONS "Timeout").
CREATE_BUDGET_SECONDS = 4.5
AI_TIMEOUT_SECONDS = 5.0
# Less than this left is not worth a call: the learner gets the manual form at once.
MIN_AI_SECONDS = 0.5


def ai_timeout(remaining: float) -> float | None:
    """Seconds ai-service may take, or None when too little time is left to ask."""
    return None if remaining < MIN_AI_SECONDS else min(AI_TIMEOUT_SECONDS, remaining)


def page_range_ok(first: int, last: int, page_count: int) -> bool:
    """FILE pages, 1-based: `1 <= first <= last <= page_count`."""
    return 1 <= first <= last <= page_count


def studied_on_ok(studied_on: datetime.date, today: datetime.date) -> bool:
    """A real study day: not in the future, not more than `LATE_LOG_DAYS` back."""
    return today - datetime.timedelta(days=LATE_LOG_DAYS) <= studied_on <= today


# The summary of an existing unit that goes into session.confirmed.v1 (contract: <= 2000).
SUMMARY_MAX_CHARS = 2000

NOTE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
}


# The first bytes each binary note type starts with; the text types have no header to check.
NOTE_MAGIC = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "application/pdf": b"%PDF-",
}
NOTE_MAGIC_MAX = max(len(magic) for magic in NOTE_MAGIC.values())


def looks_like_note(mime: str, start: bytes) -> bool:
    """Whether the file's first bytes fit the type declared. Text types always do."""
    magic = NOTE_MAGIC.get(mime)
    return magic is None or start.startswith(magic)


def cut_summary(summary: str) -> str:
    """At most `SUMMARY_MAX_CHARS` characters (not bytes): the contract's limit."""
    return summary[:SUMMARY_MAX_CHARS]


def note_key(user_id: uuid.UUID, session_id: uuid.UUID, sha256: str, mime: str) -> str:
    """Where a note file lives: built by the server from the content hash, never from a name
    the client chose (ADR-0012). The database checks the same shape."""
    return f"users/{user_id}/sessions/{session_id}/notes/{sha256}.{NOTE_EXTENSIONS[mime]}"


def ensure_ranges_ordered(ranges: Iterable[tuple[int, int]]) -> None:
    """ValueError unless every `first <= last`: the contract's JSON Schema cannot say it, so it
    is checked here, last thing before the event is enqueued."""
    if any(first > last for first, last in ranges):
        raise ValueError("page range with first > last")
