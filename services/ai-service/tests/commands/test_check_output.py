"""T9.1 (US-18 AC2, AC3, AC6; ADR-0030): the output is checked by code, labels become ids."""

import datetime
import uuid
from typing import Any

import pytest

from ai_service.commands.schema import ParseCommandRequest
from ai_service.tasks.parse_command import Labels, OutputViolation, check_output
from tests.commands.helpers import TODAY, body, output

TODAY_D = datetime.date.fromisoformat(TODAY)
REQUEST = ParseCommandRequest.model_validate(body())
LABELS = Labels.of(REQUEST)


def check(text: str) -> Any:
    return check_output(text, LABELS, TODAY_D)


def rule_of(text: str) -> str:
    with pytest.raises(OutputViolation) as raised:
        check(text)
    return raised.value.rule


def test_labels_become_the_requests_ids() -> None:
    # US-18 AC2, AC4 (core re-checks every id against the user).
    command = check(output(kind="card_merge", cards=["C2", "C5"]))
    assert command.cards == [REQUEST.cards[1].id, REQUEST.cards[4].id]


def test_single_label_and_optional_label() -> None:
    command = check(output(kind="card_add", text="Thẻ mới", section="S3"))
    assert command.section == REQUEST.sections[2].id
    assert check(output(kind="card_add", text="Thẻ mới", section=None)).section is None


def test_two_references_of_two_lists() -> None:
    command = check(output(kind="question_set_type", question="Q1", question_type="T3"))
    assert (command.question, command.question_type) == (
        REQUEST.questions[0].id,
        REQUEST.question_types[2].id,
    )


def test_unclear_is_an_answer() -> None:
    # US-18 AC3.
    assert check(output(kind="unclear", reason="unsupported")).reason == "unsupported"


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("not json", "schema"),
        ("[]", "schema"),
        ('{"result": 1}', "schema"),
        ('{"result": {"kind": "unclear", "reason": "ambiguous"}, "extra": 1}', "schema"),
        (output(kind="card_delete", card="C1"), "kind"),
        (output(reason="ambiguous"), "kind"),
        (output(kind="unclear", reason="because"), "schema"),
        (output(kind="unclear", reason="ambiguous", note="x"), "schema"),
        (output(kind="card_merge", cards=["C2"]), "schema"),  # fewer than two
        (output(kind="card_merge", cards=["C2", "C2"]), "targets"),
        (output(kind="card_merge", cards=["C2", "C99"]), "label"),  # invented label
        (output(kind="card_merge", cards=["S1", "S2"]), "label"),  # label of another list
        (output(kind="card_merge", cards="C2"), "schema"),
        (output(kind="card_edit", card=str(uuid.uuid4()), text="x"), "label"),  # a raw id
        (output(kind="card_edit", card="C1", text=" "), "schema"),
        (output(kind="section_set_pages", section="S1", from_page=9, to_page=3), "schema"),
        (output(kind="section_set_pages", section="S1", from_page=0, to_page=3), "schema"),
        (output(kind="card_split", card="C1", parts=9), "schema"),
        (output(kind="question_relink", question="Q1", card="C1", section="S1"), "schema"),
        (output(kind="question_relink", question="Q1", card=None, section=None), "schema"),
        (output(kind="suggest_defer_subject", subject="J1", until="2025-01-01"), "until"),
        (output(kind="suggest_defer_subject", subject="J1", until="2030-01-01"), "until"),
        (output(kind="suggest_defer_subject", subject="J1", until="soon"), "schema"),
        (output(kind="section_mark", sections=[], studied=True), "schema"),
    ],
)
def test_broken_outputs_are_refused_with_a_rule(text: str, rule: str) -> None:
    # US-18 AC3, AC6: nothing outside the fixed list, no invented target, no guess.
    assert rule_of(text) == rule


def test_a_filter_ending_today_or_within_a_year_is_allowed() -> None:
    check(output(kind="suggest_only_subject", subject="J1", until=TODAY))
    check(output(kind="suggest_defer_subject", subject="J2", until="2026-11-05"))
