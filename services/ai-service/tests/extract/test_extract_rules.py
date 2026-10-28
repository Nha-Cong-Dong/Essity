"""T4.10: the rules x1..x9 that check a model's output, and the request's normalization."""

import datetime
import json
from typing import Any

import pytest
from pydantic import ValidationError

from ai_service.tasks.extract_models import ExtractRequest
from ai_service.tasks.extract_session import OutputViolation, check_output, normalize_documents
from tests.extract.helpers import TODAY, docs_of, document, extract_body, output, rng


def violation(text: str, body: dict[str, Any] | None = None) -> str:
    docs = docs_of(body or extract_body(documents=[document(), document("slide c3")]))
    with pytest.raises(OutputViolation) as raised:
        check_output(text, docs, TODAY)
    return raised.value.rule


def ok(text: str, body: dict[str, Any] | None = None):
    docs = docs_of(body or extract_body(documents=[document(), document("slide c3")]))
    return check_output(text, docs, TODAY)


def test_valid_proposal_is_accepted() -> None:
    outcome = ok(output())
    assert outcome.status == "proposed"
    assert (outcome.ranges[0].pages.start, outcome.ranges[0].pages.end) == (51, 66)


@pytest.mark.parametrize(
    "text",
    ["", "not json", "[]", output() + "x", '{"status": "proposed"}'],
)
def test_x1_broken_json_or_missing_fields(text: str) -> None:
    assert violation(text) == "x1"


def test_x1_extra_field_and_wrong_types() -> None:
    value = json.loads(output())
    assert violation(json.dumps({**value, "raw": 1})) == "x1"
    value["ranges"][0]["from_page"] = "43"  # strict: a string is not a page
    assert violation(json.dumps(value)) == "x1"
    value = json.loads(output())
    value["ranges"][0]["depth"] = "medium"
    assert violation(json.dumps(value)) == "x1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"ranges": []},  # proposed without ranges
        {"ranges": [rng(basis="file", from_page=i, to_page=i) for i in range(1, 8)]},  # 7 > 6
        {"question": "Hỏi gì?"},
        {"reason": "missing_info"},
        {"candidates": ["D1"]},
    ],
)
def test_x2_proposed_fields(overrides: dict[str, Any]) -> None:
    assert violation(output(**overrides)) == "x2"


@pytest.mark.parametrize(
    "overrides",
    [{"ranges": [rng()]}, {"question": "Gì?"}, {"reason": "missing_info"}, {"candidates": ["D1"]}],
)
def test_x2_note_only_has_nothing_else(overrides: dict[str, Any]) -> None:
    assert violation(output("note_only", **overrides)) == "x2"


def clarify(**overrides: Any) -> str:
    base: dict[str, Any] = {"question": "Bạn học chương nào?", "reason": "ambiguous_range"}
    base.update(overrides)
    return output("clarify", **base)


def test_x2_clarify_needs_question_reason_and_no_ranges_or_day() -> None:
    assert ok(clarify()).status == "clarify"
    assert violation(clarify(ranges=[rng()])) == "x2"
    assert violation(clarify(question=None)) == "x2"
    assert violation(clarify(reason=None)) == "x2"
    assert violation(clarify(studied_day={"days_ago": 1, "date": None})) == "x2"


def test_x3_unknown_document_label_or_candidate() -> None:
    assert violation(output(ranges=[rng("D3")])) == "x3"
    assert violation(output(ranges=[rng("slide")])) == "x3"
    assert violation(clarify(candidates=["D9"])) == "x3"
    assert violation(clarify(reason="ambiguous_document", candidates=["D1", "D1"])) == "x3"


def test_x4_section_of_another_document_or_missing() -> None:
    bad = rng(kind="section", basis=None, from_page=None, to_page=None, from_section="D2.S1")
    assert violation(output(ranges=[bad])) == "x4"  # D1's range pointing into D2
    bad = rng("D1", "section", basis=None, from_page=None, to_page=None, from_section="D1.S40")
    assert violation(output(ranges=[bad])) == "x4"


def test_x4_section_whose_toc_entry_has_no_page_is_dropped() -> None:
    body = extract_body(documents=[document(toc=[("Phụ lục", 0, None), ("Chương 1", 0, 9)])])
    bad = rng("D1", "section", basis=None, from_page=None, to_page=None, from_section="D1.S1")
    ok_ref = rng("D1", "section", basis=None, from_page=None, to_page=None, from_section="D1.S1")
    # S1 is "Chương 1": the entry with no page is not in the list, so labels shift.
    assert ok(output(ranges=[ok_ref]), body).ranges[0].pages.start == 9
    bad["from_section"] = "D1.S2"
    assert violation(output(ranges=[bad]), body) == "x4"


@pytest.mark.parametrize(
    "day",
    [
        {"days_ago": 1, "date": "2026-10-27"},  # both
        {"days_ago": -1, "date": None},
        {"days_ago": 367, "date": None},
        {"days_ago": None, "date": "2026-10-29"},  # tomorrow
        {"days_ago": None, "date": "2025-10-26"},  # 367 days ago
        {"days_ago": None, "date": "28/10/2026"},
        {"days_ago": None, "date": "20261027"},
        {"days_ago": None, "date": "2026-02-30"},
    ],
)
def test_x5_bad_day(day: dict[str, Any]) -> None:
    assert violation(output(studied_day=day)) == "x5"


def test_x5_days_ago_and_date_are_worked_out_by_code() -> None:
    assert ok(output(studied_day={"days_ago": 1, "date": None})).studied_on == (
        TODAY - datetime.timedelta(days=1)
    )
    assert ok(output(studied_day={"days_ago": None, "date": "2026-10-20"})).studied_on == (
        datetime.date(2026, 10, 20)
    )
    assert ok(output()).studied_on is None
    assert ok(output(studied_day={"days_ago": 0, "date": None})).studied_on == TODAY
    assert ok(output(studied_day={"days_ago": 366, "date": None})).studied_on == (
        TODAY - datetime.timedelta(days=366)
    )


def test_x6_the_same_range_twice_but_overlap_is_fine() -> None:
    assert violation(output(ranges=[rng(), rng()])) == "x6"
    assert ok(output(ranges=[rng(), rng(depth="unclear")])).status == "proposed"
    inside = rng(from_page=45, to_page=50, depth="unclear")
    assert len(ok(output(ranges=[rng(), inside])).ranges) == 2


def test_x7_out_of_range_reaches_the_rule() -> None:
    assert violation(output(ranges=[rng(basis="file", from_page=70, to_page=90)])) == "x7"


def test_x8_continue_without_a_last_session() -> None:
    cont = rng(kind="continue", basis="printed", from_page=None, to_page=60)
    assert violation(output(ranges=[cont])) == "x8"
    body = extract_body(documents=[document(last_end_page=50)])
    assert ok(output(ranges=[cont]), body).ranges[0].pages.start == 51


@pytest.mark.parametrize(
    "question",
    ["", "   ", "Một? Hai?", "Dòng một\nDòng hai?", "x" * 301, "Dòng\rhai?"],
)
def test_x9_question_shape(question: str) -> None:
    assert violation(clarify(question=question)) == "x9"


def test_x9_question_boundaries_and_ambiguous_document_needs_two() -> None:
    assert ok(clarify(question="x" * 299 + "?")).status == "clarify"
    assert violation(clarify(reason="ambiguous_document", candidates=["D1"])) == "x9"
    assert ok(clarify(reason="ambiguous_document", candidates=["D1", "D2"])).status == "clarify"


# --- The request ---------------------------------------------------------------------------


def test_request_limits_are_422_without_echoing_the_input() -> None:
    cases: list[dict[str, Any]] = [
        extract_body(description="   "),
        extract_body(description="a\x00b"),
        extract_body(description="x" * 2001),
        extract_body(documents=[document(f"tài liệu {n}") for n in range(13)]),
        extract_body(documents=[]),
        extract_body(documents=[document(labels=["1", "2"])]),
        extract_body(documents=[document(toc=[("x", 0, 99)])]),
        extract_body(documents=[document(last_end_page=81)]),
        extract_body(documents=[{**document(), "extra": 1}]),
    ]
    twin = document()
    cases.append(
        extract_body(documents=[twin, {**document("b"), "document_id": twin["document_id"]}])
    )
    big = [(f"mục {n}", 0, 1) for n in range(5000)]
    cases.append(extract_body(documents=[document(f"d{n}", toc=big) for n in range(2)]))
    for body in cases:
        with pytest.raises(ValidationError) as raised:
            ExtractRequest.model_validate(body)
        for error in raised.value.errors():
            assert "secret-marker" not in str(error.get("msg"))


def test_real_t47_toc_shape_is_accepted() -> None:
    # What T4.7 writes: level from 0, a title that may be empty or long, labels that may be
    # empty or long, 5000 entries in one document.
    toc = [("", 0, 3), ("t" * 500, 16, 4)] + [(f"m{n}", 1, None) for n in range(4998)]
    labels = ["", "x" * 128] + ["1"] * 78
    request = ExtractRequest.model_validate(
        extract_body(documents=[document(toc=toc, labels=labels)])
    )
    assert len(request.documents[0].toc) == 5000


def test_toc_is_normalized_for_the_prompt() -> None:
    toc: list[tuple[str, int, int | None]] = [
        ("", 0, 1),  # no title: dropped
        ("   ", 0, 1),
        ("Không trang", 0, None),  # no page: dropped
        ("Sâu", 3, 5),  # level 3: dropped
        ("Chương  một\n|S9|x", 0, 9),  # whitespace and the separator collapse
        ("Dài " + "d" * 300, 1, 10),
    ]
    [doc] = normalize_documents(
        ExtractRequest.model_validate(extract_body(documents=[document(toc=toc)]))
    )
    assert [section.label for section in doc.sections] == ["S1", "S2"]
    assert doc.sections[0].title == "Chương một S9 x"
    assert len(doc.sections[1].title) == 120


def test_toc_too_long_keeps_the_shallowest_in_original_order() -> None:
    toc = [(f"s{n}", n % 2, n + 1) for n in range(600)]
    [doc] = normalize_documents(
        ExtractRequest.model_validate(
            extract_body(documents=[document(toc=toc, page_count=700, labels=None)])
        )
    )
    assert len(doc.sections) == 300
    assert all(section.level == 0 for section in doc.sections)  # 300 level-0 entries exist
    pages = [section.page for section in doc.sections]
    assert pages == sorted(pages)


def test_total_sections_stay_under_800() -> None:
    toc = [(f"s{n}", 0, n + 1) for n in range(300)]
    docs = normalize_documents(
        ExtractRequest.model_validate(
            extract_body(
                documents=[
                    document(f"d{n}", toc=toc, page_count=400, labels=None) for n in range(12)
                ]
            )
        )
    )
    assert sum(len(doc.sections) for doc in docs) <= 800
