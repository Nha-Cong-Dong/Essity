"""Pure rules of a study session (T4.12)."""

import datetime
import uuid
from typing import get_args

import pytest

from core_api.domain.study_session import (
    NOTE_EXTENSIONS,
    ai_timeout,
    cut_summary,
    ensure_ranges_ordered,
    note_key,
    page_range_ok,
    studied_on_ok,
)
from core_api.messaging.envelope import NoteFile

TODAY = datetime.date(2026, 10, 22)


def test_note_extensions_cover_exactly_the_contracts_mime_types() -> None:
    mimes = get_args(NoteFile.model_fields["mime"].annotation)
    assert set(NOTE_EXTENSIONS) == set(mimes)


def test_note_key_is_built_from_the_hash() -> None:
    user, session = uuid.uuid4(), uuid.uuid4()
    assert note_key(user, session, "ab" * 32, "text/markdown") == (
        f"users/{user}/sessions/{session}/notes/{'ab' * 32}.md"
    )


def test_summary_is_cut_by_characters() -> None:
    assert cut_summary("ế" * 2001) == "ế" * 2000
    assert cut_summary("ngắn") == "ngắn"


@pytest.mark.parametrize(
    ("first", "last", "count", "ok"),
    [(1, 1, 1, True), (3, 9, 40, True), (9, 3, 40, False), (0, 3, 40, False), (1, 41, 40, False)],
)
def test_page_range_ok(first: int, last: int, count: int, ok: bool) -> None:
    assert page_range_ok(first, last, count) is ok


def test_ensure_ranges_ordered_refuses_a_reversed_range() -> None:
    ensure_ranges_ordered([(1, 1), (2, 5)])
    with pytest.raises(ValueError):
        ensure_ranges_ordered([(1, 2), (5, 4)])


@pytest.mark.parametrize(("days_back", "ok"), [(0, True), (366, True), (367, False), (-1, False)])
def test_studied_on_window(days_back: int, ok: bool) -> None:
    assert studied_on_ok(TODAY - datetime.timedelta(days=days_back), TODAY) is ok


@pytest.mark.parametrize(("left", "expected"), [(4.5, 4.5), (10.0, 5.0), (0.5, 0.5), (0.4, None)])
def test_ai_timeout_is_what_is_left_up_to_five_seconds(left: float, expected: float | None) -> None:
    assert ai_timeout(left) == expected
