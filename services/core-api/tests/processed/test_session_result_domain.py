"""T4.17: reading the result file (session-result.v1) and cleaning it before the database."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from result_builders import anchor, encode, question, result, unit

from core_api.domain.session_result import CleanResult, ResultRefused, clean, parse_result

SESSION = uuid.uuid4()
DOC = uuid.uuid4()
U1, U2, U3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def cleaned(**over: Any) -> CleanResult:
    parsed = parse_result(encode(result(SESSION, **over)))
    return clean(parsed, study_session_id=SESSION, documents={DOC})


def _missing_field(body: dict[str, Any]) -> None:
    body.pop("merges")


def _extra_field(body: dict[str, Any]) -> None:
    body["extra"] = 1


def _version(body: dict[str, Any]) -> None:
    body["version"] = 2


def _level_four(body: dict[str, Any]) -> None:
    body["questions"].append(question([U1], level=4))


def _kind(body: dict[str, Any]) -> None:
    body["units"].append(unit(U1, DOC, kind="poem"))


def _huge_page(body: dict[str, Any]) -> None:
    body["units"].append(unit(U1, DOC, anchors=[anchor(DOC, page_no=2**31)]))


def _huge_offset(body: dict[str, Any]) -> None:
    body["units"].append(unit(U1, DOC, anchors=[anchor(DOC, end=2**31)]))


def _bad_uuid(body: dict[str, Any]) -> None:
    body["units"].append(unit(U1, DOC) | {"unit_id": "not-a-uuid"})


@pytest.mark.parametrize(
    "mutate",
    [
        _missing_field,
        _extra_field,
        _version,
        _level_four,
        _kind,
        _bad_uuid,
        _huge_page,
        _huge_offset,
    ],
)
def test_result_breaking_the_schema_is_refused(mutate: Callable[[dict[str, Any]], None]) -> None:
    body = result(SESSION)
    mutate(body)
    with pytest.raises(ValidationError):
        parse_result(encode(body))


def test_result_that_is_not_json_is_refused() -> None:
    with pytest.raises(ValidationError):
        parse_result(b"\xff not json")


def test_session_id_in_the_file_must_be_the_sessions() -> None:
    parsed = parse_result(encode(result(uuid.uuid4())))
    with pytest.raises(ResultRefused):
        clean(parsed, study_session_id=SESSION, documents=set())


def test_duplicate_unit_id_refuses_the_result() -> None:
    with pytest.raises(ResultRefused):
        cleaned(units=[unit(U1, DOC), unit(U1, DOC)])


def test_level_rules_rechecked() -> None:
    out = cleaned(
        units=[unit(U1, DOC), unit(U2, DOC), unit(U3, DOC)],
        questions=[
            question([U1, U2], 1, prompt="l1 two units"),
            question([U1], 3, prompt="l3 one unit"),
            question([U1, U2, U3], 2, prompt="l2 three units"),
            question([U1, U2], 2, prompt="good l2 two units"),
            question([U1, uuid.uuid4()], 3, prompt="l3 unit outside the file"),
            question([U1], 1, prompt="good l1"),
            question([U1], 2, prompt="good l2"),
            question([U1, U2], 3, prompt="good l3"),
        ],
    )
    assert [q.prompt for q in out.questions] == [
        "good l2 two units",
        "good l1",
        "good l2",
        "good l3",
    ]
    assert out.dropped_questions == 4


def test_text_has_no_nul_and_title_is_cut() -> None:
    body = result(
        SESSION,
        units=[
            unit(
                U1,
                DOC,
                title="Tên\x00 dài" + "x" * 300,
                summary="Tóm\x00 tắt",
                anchors=[anchor(DOC, quote_text="trích\x00 dẫn")],
            )
        ],
        questions=[
            question(
                [U1], prompt="Hỏi\x00 gì", reference_answer="Đáp\x00 án", rubric="Tiêu\x00 chí"
            )
        ],
    )
    out = clean(parse_result(encode(body)), study_session_id=SESSION, documents={DOC})
    texts = [out.units[0].title, out.units[0].summary, out.units[0].anchors[0].quote_text]
    texts += [out.questions[0].prompt, out.questions[0].reference_answer, out.questions[0].rubric]
    for text in texts:
        assert "\x00" not in text
    assert len(out.units[0].title) == 200


def test_a_lone_surrogate_is_refused_by_the_parser() -> None:
    # Postgres would refuse it; the JSON parser does first, so the whole result is refused (Y7).
    raw = encode(result(SESSION, units=[unit(U1, DOC, title="AAA")])).replace(b"AAA", b"A\\ud800B")
    with pytest.raises(ValidationError):
        parse_result(raw)


def test_item_blank_after_nul_removed_is_dropped() -> None:
    out = cleaned(
        units=[unit(U1, DOC, title="\x00"), unit(U2, DOC)],
        questions=[question([U2], prompt="\x00"), question([U2], reference_answer="\x00 ")],
    )
    assert [u.unit_id for u in out.units] == [U2]
    assert out.questions == []


def test_anchor_rules_drop_bad_anchors_and_units_left_without_any() -> None:
    out = cleaned(
        units=[
            unit(U1, DOC, anchors=[anchor(uuid.uuid4())]),  # document not the user's
            unit(U2, DOC, anchors=[anchor(DOC, start=9, end=3)]),  # start after end
            unit(U3, DOC, anchors=[anchor(DOC), anchor(None), anchor(DOC, page_no=None)]),
        ],
    )
    assert [u.unit_id for u in out.units] == [U3]
    assert len(out.units[0].anchors) == 1
    assert out.dropped_anchors == 4


def test_notes_anchor_has_no_document_and_needs_no_page() -> None:
    notes = anchor(None, source="notes", page_no=None)
    out = cleaned(units=[unit(U1, DOC, anchors=[notes, anchor(DOC, source="notes")])])
    assert [a.source for a in out.units[0].anchors] == ["notes"]


def test_question_on_a_dropped_unit_is_dropped_and_the_rest_kept() -> None:
    out = cleaned(
        units=[unit(U1, DOC, anchors=[anchor(uuid.uuid4())]), unit(U2, DOC)],
        questions=[question([U1]), question([U2]), question([U1, U2], 3, prompt="l3")],
    )
    assert [u.unit_id for u in out.units] == [U2]
    assert [q.unit_ids for q in out.questions] == [(U2,)]


def test_merges_keep_only_valid_anchors_and_section_id_is_not_kept() -> None:
    existing = uuid.uuid4()
    section = uuid.uuid4()
    out = cleaned(
        units=[unit(U1, DOC, section_id=str(section))],
        merges=[
            {"existing_unit_id": str(existing), "anchors": [anchor(DOC), anchor(uuid.uuid4())]},
            {"existing_unit_id": str(uuid.uuid4()), "anchors": [anchor(uuid.uuid4())]},
        ],
    )
    assert [(m.existing_unit_id, len(m.anchors)) for m in out.merges] == [(existing, 1)]
    assert out.units[0].section_id is None
