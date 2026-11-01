"""`GET /v1/subjects/{id}/practice-types` (T8.6b, US-16 AC4-AC9): per question type, the mastery
and the sensitivity of the current user. Reads only. Copy is neutral: no rank, no penalty."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core_api.api.deps import VerifiedUser, verified_user
from core_api.db.session import DbSession
from core_api.domain.mastery_type import load_config, summarize
from core_api.repositories.practice_types import PracticeTypeRepository
from core_api.repositories.subject import SubjectRepository

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])


class PracticeTypeOut(BaseModel):
    type_id: uuid.UUID
    name: str
    mastery: float | None  # 0..1, None = not enough data
    attempts_counted: int
    mastery_line: str
    sensitivity: Literal["not_enough_data", "faster", "near", "slower"]
    sensitivity_line: str
    reference_seconds: float
    ref_origin: str
    formula_version: str


@router.get("/subjects/{subject_id}/practice-types")
def list_practice_types(
    subject_id: uuid.UUID, user: VerifiedUser, session: DbSession
) -> list[PracticeTypeOut]:
    if SubjectRepository(session, user.id).get(subject_id) is None:
        raise HTTPException(status_code=404, detail="subject_not_found")
    repo = PracticeTypeRepository(session, user.id)
    config = load_config()
    attempts = repo.attempts_by_type(subject_id)
    out: list[PracticeTypeOut] = []
    for kind in repo.of_subject(subject_id):
        s = summarize(kind.ref_time_s, kind.ref_origin, attempts.get(kind.id, []), config)
        out.append(
            PracticeTypeOut(
                type_id=kind.id,
                name=kind.name,
                mastery=s.mastery,
                attempts_counted=s.attempts_counted,
                mastery_line=s.mastery_line,
                sensitivity=s.sensitivity.value,  # pyright: ignore[reportArgumentType]
                sensitivity_line=s.sensitivity_line,
                reference_seconds=s.reference_seconds,
                ref_origin=s.ref_origin,
                formula_version=s.formula_version,
            )
        )
    return out
