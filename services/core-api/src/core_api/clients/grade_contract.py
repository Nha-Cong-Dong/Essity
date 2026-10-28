"""ai-service's POST /v1/grade answer, as core-api reads it (T2.12 contract, T2.13). core-api cannot
import ai-service (scripts/check_cross_imports.py), so this is its own copy, strict: an answer
outside the contract is not trusted (R03 layer 2 starts here)."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

Verdict = Literal["correct", "partial", "incorrect"]
# "fake": the fake grader (only valid in local and test, R41); "none": an empty answer, graded
# incorrect by code without a model (ai-service decision D13).
Provider = Literal["anthropic", "fake", "none"]


class UnitVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    unit_id: uuid.UUID
    verdict: Verdict


class GradeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=False)
    provider: Provider
    model: str | None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None
    overall: Verdict
    understanding: Literal[1, 2, 3] | None
    missing: list[str]
    units: list[UnitVerdict]
    anchors_used: list[uuid.UUID]


class GradedResult(BaseModel):
    """The result file ai-service writes for a queued grading (contracts/files/grade-result.v1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["graded"]
    response: GradeResponse


class FailedResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["failed"]
    failure: Literal["invalid", "disabled"]


GRADE_RESULT: TypeAdapter[GradedResult | FailedResult] = TypeAdapter(
    Annotated[GradedResult | FailedResult, Field(discriminator="status")]
)
