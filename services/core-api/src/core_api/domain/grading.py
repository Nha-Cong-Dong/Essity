"""The pure part of grading (T2.13): the request core-api sends to ai-service's /v1/grade, and the
check of what comes back, before anything is written. No database, no network.

The request is checked against ai-service's limits first (plan D-6, 🟡5): a request it would
refuse with 422 could never be graded, and "Chấm lại" would loop. The answer is checked again in
core (R03 layer 2, R41 layer 2, 🟡6): the unit set must be exactly the one sent, each anchor one
that was sent, `overall` and `understanding` consistent, and the fake grader only trusted in
local and test.
"""

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from core_api.api.text import storable_text
from core_api.clients.grade_contract import GradeResponse, Verdict

# ai-service's limits (its tasks/grade_models.py, PR B decision G6).
MAX_ANSWER_CHARS = 4000
MAX_UNITS = 5
MAX_ANCHORS_PER_UNIT = 5
MAX_QUOTE_CHARS = 12000
MAX_QUESTION_CHARS = 4000
# Where the fake grader's answer may be stored (R41 layer 2).
FAKE_ENVIRONMENTS = frozenset({"local", "test"})

# "system": "Không nhớ", graded without the AI (US-04 AC2).
Source = Literal["ai", "fake", "system"]
Overall = Literal["correct", "partial", "incorrect", "forgot"]


class RequestRefused(ValueError):
    """The request is outside ai-service's limits: grading is "invalid" without a call."""


class ResponseRefused(ValueError):
    """ai-service's answer does not match the request: grading is "invalid", nothing written."""


@dataclass(frozen=True)
class AnchorIn:
    anchor_id: uuid.UUID
    quote_text: str


@dataclass(frozen=True)
class UnitIn:
    unit_id: uuid.UUID
    title: str
    anchors: Sequence[AnchorIn]


@dataclass(frozen=True)
class QuestionIn:
    text: str
    rubric: Any  # the question's JSONB rubric, or None
    reference_answer: str


@dataclass(frozen=True)
class CheckedGrade:
    source: Source
    overall: Overall
    understanding: int | None
    missing: list[str]
    units: Mapping[uuid.UUID, Verdict]
    anchors_used: list[uuid.UUID]
    run_id: uuid.UUID | None


def build_request(
    *,
    user_id: uuid.UUID,
    subject_id: uuid.UUID,
    attempt_id: uuid.UUID,
    question: QuestionIn,
    answer: str,
    units: Sequence[UnitIn],
) -> dict[str, object]:
    """The JSON body of POST /v1/grade, or RequestRefused when ai-service would refuse it."""
    # A text rubric (the session result, T4.17) goes as it is; json.dumps would quote it.
    rubric = (
        question.rubric
        if question.rubric is None or isinstance(question.rubric, str)
        else json.dumps(question.rubric, ensure_ascii=False)
    )
    texts = [question.text, question.reference_answer, rubric or ""]
    if any(len(text) > MAX_QUESTION_CHARS for text in texts) or len(answer) > MAX_ANSWER_CHARS:
        raise RequestRefused("text over the limit")
    if not 1 <= len(units) <= MAX_UNITS:
        raise RequestRefused("unit count")
    if any(not 1 <= len(unit.anchors) <= MAX_ANCHORS_PER_UNIT for unit in units):
        raise RequestRefused("anchor count")
    if sum(len(a.quote_text) for unit in units for a in unit.anchors) > MAX_QUOTE_CHARS:
        raise RequestRefused("source text over the limit")
    return {
        "user_id": str(user_id),
        "subject_id": str(subject_id),
        "attempt_id": str(attempt_id),
        "question": {
            "text": question.text,
            "rubric": rubric,
            "reference_answer": question.reference_answer,
        },
        "answer": answer,
        "units": [
            {
                "unit_id": str(unit.unit_id),
                "title": unit.title,
                "anchors": [
                    {"anchor_id": str(a.anchor_id), "quote_text": a.quote_text}
                    for a in unit.anchors
                ],
            }
            for unit in units
        ],
    }


def overall_of(verdicts: Sequence[Verdict]) -> Verdict:
    """All correct is correct, all incorrect is incorrect, anything else partial (T2.12)."""
    if all(v == "correct" for v in verdicts):
        return "correct"
    if all(v == "incorrect" for v in verdicts):
        return "incorrect"
    return "partial"


def check_response(
    answer: GradeResponse, *, units: Sequence[UnitIn], environment: str
) -> CheckedGrade:
    """ai-service's answer, checked against the request it answers; ResponseRefused otherwise."""
    if answer.provider == "fake" and environment not in FAKE_ENVIRONMENTS:
        raise ResponseRefused("fake grader outside local and test")
    sent = [unit.unit_id for unit in units]
    got = [unit.unit_id for unit in answer.units]
    if len(got) != len(set(got)) or set(got) != set(sent):
        raise ResponseRefused("unit set")
    verdicts: dict[uuid.UUID, Verdict] = {unit.unit_id: unit.verdict for unit in answer.units}
    if answer.overall != overall_of([verdicts[u] for u in sent]):
        raise ResponseRefused("overall")
    if answer.understanding is not None and answer.overall == "incorrect":
        raise ResponseRefused("understanding")
    for point in answer.missing:
        # Postgres refuses NUL in JSONB, and its error quotes the row (a piece of the answer)
        # into the span (review 🟡1, ADR-0013): refused here, before any write.
        try:
            storable_text(point)
        except ValueError:
            raise ResponseRefused("missing") from None
    anchors = {a.anchor_id for unit in units for a in unit.anchors}
    used = list(dict.fromkeys(answer.anchors_used))
    if not set(used) <= anchors:
        raise ResponseRefused("anchors_used")
    return CheckedGrade(
        source="fake" if answer.provider == "fake" else "ai",
        overall=answer.overall,
        understanding=answer.understanding,
        missing=list(answer.missing),
        units=verdicts,
        anchors_used=used,
        run_id=answer.run_id,
    )
