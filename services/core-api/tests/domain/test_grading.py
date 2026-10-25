"""T2.13: the pure part of grading (plan, commit 5): the request core sends, checked against
ai-service's limits before any call (D-6, 🟡5), and ai-service's answer checked again in core (R03
layer 2, R41 layer 2, 🟡6) before anything is written."""

import uuid
from typing import Any

import pytest

from core_api.clients.grade_contract import GradeResponse
from core_api.domain.grading import (
    AnchorIn,
    QuestionIn,
    RequestRefused,
    ResponseRefused,
    UnitIn,
    build_request,
    check_response,
)

USER, SUBJECT, ATTEMPT = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
U1, U2 = uuid.uuid4(), uuid.uuid4()
A1, A2 = uuid.uuid4(), uuid.uuid4()
QUESTION = QuestionIn(
    text="TCP là gì?", rubric={"y": ["tin cậy"]}, reference_answer="Giao thức tin cậy."
)
UNITS = [
    UnitIn(U1, "TCP", [AnchorIn(A1, "TCP là giao thức tin cậy.")]),
    UnitIn(U2, "UDP", [AnchorIn(A2, "UDP không bảo đảm.")]),
]


def request(**changes: object) -> dict[str, object]:
    args: dict[str, object] = {
        "user_id": USER,
        "subject_id": SUBJECT,
        "attempt_id": ATTEMPT,
        "question": QUESTION,
        "answer": "Tin cậy",
        "units": UNITS,
    }
    args.update(changes)
    return build_request(**args)  # type: ignore[arg-type]


# US-05 AC8. Red when: a unit's source is left out, or the rubric is not sent as text.
def test_us05_ac8_request_carries_every_unit_and_anchor() -> None:
    body: Any = request()
    assert [u["unit_id"] for u in body["units"]] == [str(U1), str(U2)]
    assert body["units"][0]["anchors"] == [
        {"anchor_id": str(A1), "quote_text": "TCP là giao thức tin cậy."}
    ]
    assert body["question"]["rubric"] == '{"y": ["tin cậy"]}'
    assert body["attempt_id"] == str(ATTEMPT)


# Plan D-6, 🟡5. Red when: a request ai-service would refuse (422 forever) is sent.
@pytest.mark.parametrize(
    "changes",
    [
        {"answer": "x" * 4001},
        {"units": [UnitIn(uuid.uuid4(), f"u{n}", [AnchorIn(uuid.uuid4(), "q")]) for n in range(6)]},
        {"units": [UnitIn(U1, "TCP", [AnchorIn(uuid.uuid4(), "q") for _ in range(6)])]},
        {"units": [UnitIn(U1, "TCP", [])]},
        {"units": [UnitIn(U1, "TCP", [AnchorIn(A1, "q" * 12001)])]},
        {"question": QuestionIn(text="x" * 4001, rubric=None, reference_answer="a")},
        {"question": QuestionIn(text="q", rubric=None, reference_answer="a" * 4001)},
        {"question": QuestionIn(text="q", rubric={"k": "x" * 4000}, reference_answer="a")},
    ],
)
def test_t213_requests_outside_the_limits_are_refused_before_any_call(
    changes: dict[str, object],
) -> None:
    with pytest.raises(RequestRefused):
        request(**changes)


def response(**changes: object) -> GradeResponse:
    base: dict[str, object] = {
        "provider": "anthropic",
        "model": "claude-haiku-5-5",
        "prompt_version": "v1",
        "run_id": str(uuid.uuid4()),
        "llm_call_id": str(uuid.uuid4()),
        "overall": "partial",
        "understanding": 2,
        "missing": ["UDP"],
        "units": [
            {"unit_id": str(U1), "verdict": "correct"},
            {"unit_id": str(U2), "verdict": "incorrect"},
        ],
        "anchors_used": [str(A1)],
    }
    base.update(changes)
    return GradeResponse.model_validate(base)


def check(answer: GradeResponse, environment: str = "production") -> object:
    return check_response(answer, units=UNITS, environment=environment)


def test_t213_a_valid_answer_passes() -> None:
    verdicts = check(response())
    assert verdicts.units == {U1: "correct", U2: "incorrect"}  # type: ignore[attr-defined]
    assert verdicts.anchors_used == [A1]  # type: ignore[attr-defined]
    assert verdicts.source == "ai"  # type: ignore[attr-defined]


# R03 layer 2, 🟡6. Red when: an answer that does not match what was sent is written.
@pytest.mark.parametrize(
    "changes",
    [
        {"units": [{"unit_id": str(U1), "verdict": "correct"}]},
        {
            "units": [
                {"unit_id": str(U1), "verdict": "correct"},
                {"unit_id": str(U1), "verdict": "incorrect"},
                {"unit_id": str(U2), "verdict": "incorrect"},
            ]
        },
        {
            "units": [
                {"unit_id": str(U1), "verdict": "correct"},
                {"unit_id": str(uuid.uuid4()), "verdict": "correct"},
            ]
        },
        {"anchors_used": [str(uuid.uuid4())]},
        {"overall": "incorrect", "understanding": 2},
        {"overall": "correct"},
    ],
)
def test_r03_layer_2_refuses_an_answer_that_does_not_match(changes: dict[str, object]) -> None:
    with pytest.raises(ResponseRefused):
        check(response(**changes))


def test_t213_repeated_anchors_are_kept_once() -> None:
    assert check(response(anchors_used=[str(A1), str(A1)])).anchors_used == [A1]  # type: ignore[attr-defined]


# R41 layer 2. Red when: the fake grader's answer is trusted outside local and test.
def test_r41_fake_outside_local_and_test_is_refused() -> None:
    with pytest.raises(ResponseRefused):
        check(response(provider="fake"), environment="production")
    assert check(response(provider="fake"), environment="local").source == "fake"  # type: ignore[attr-defined]


# Plan D-3. Red when: an empty answer graded by code is stored as anything but an AI grade.
def test_t213_provider_none_is_stored_as_ai() -> None:
    answer = response(
        provider="none",
        model=None,
        llm_call_id=None,
        overall="incorrect",
        understanding=None,
        units=[
            {"unit_id": str(U1), "verdict": "incorrect"},
            {"unit_id": str(U2), "verdict": "incorrect"},
        ],
        anchors_used=[],
    )
    assert check(answer).source == "ai"  # type: ignore[attr-defined]
