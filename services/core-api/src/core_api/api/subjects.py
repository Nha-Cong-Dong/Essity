"""`/v1/subjects`: a subject with its exam date (US-01, T1.19).

Created with exactly two fields, name and exam date (AC1). The exam date must be after the
user's current learning day (AC2): an exam today is refused. A subject whose exam is over can
still be renamed: PATCH checks the date only when it changes. Someone else's subject, a deleted
one and one that never existed all answer the same 404.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Self
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    StrictStr,
    model_validator,
)

from core_api.api.deps import VerifiedUser, verified_user
from core_api.db.models import Exam, Subject, User
from core_api.db.session import DbSession
from core_api.domain.subjects import (
    ExamDateNotInFutureError,
    normalize_subject_name,
    validate_exam_date,
)
from core_api.repositories.subject import SubjectRepository

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

NAME_MAX = 200  # subject.name is String(200)


def _name(value: str) -> str:
    # JSON can carry a lone surrogate (a "\ud800" escape): Python holds it, UTF-8 cannot store it.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("name must be valid Unicode text") from None
    value = normalize_subject_name(value)
    if not 1 <= len(value) <= NAME_MAX:
        raise ValueError(f"name must be 1 to {NAME_MAX} characters")
    return value


def _date_text(value: object) -> object:
    # JSON has no date type: only an ISO string, never a number read as a timestamp.
    if not isinstance(value, str):
        raise ValueError("exam_date must be an ISO date string")
    return value


Name = Annotated[StrictStr, AfterValidator(_name)]
ExamDate = Annotated[date, BeforeValidator(_date_text)]


class SubjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    exam_date: ExamDate


class SubjectChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    exam_date: ExamDate | None = None

    @model_validator(mode="after")
    def something_to_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("give name, exam_date or both")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("name and exam_date cannot be null")
        return self


class SubjectOut(BaseModel):
    id: uuid.UUID
    name: str
    exam_date: date
    created_at: datetime


def _out(subject: Subject, exam: Exam) -> SubjectOut:
    return SubjectOut(
        id=subject.id, name=subject.name, exam_date=exam.exam_date, created_at=subject.created_at
    )


def _check_exam_date(exam_date: date, user: User) -> None:
    try:
        validate_exam_date(
            exam_date, datetime.now(UTC), ZoneInfo(user.timezone), user.day_start_hour
        )
    except ExamDateNotInFutureError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="exam_date_not_in_future"
        ) from None


@router.post("/subjects", status_code=status.HTTP_201_CREATED)
def create_subject(body: SubjectIn, user: VerifiedUser, session: DbSession) -> SubjectOut:
    _check_exam_date(body.exam_date, user)
    subject, exam = SubjectRepository(session, user.id).create_with_exam(body.name, body.exam_date)
    return _out(subject, exam)


@router.get("/subjects")
def list_subjects(user: VerifiedUser, session: DbSession) -> list[SubjectOut]:
    return [_out(s, e) for s, e in SubjectRepository(session, user.id).list_with_exams()]


@router.patch("/subjects/{subject_id}")
def change_subject(
    subject_id: uuid.UUID, body: SubjectChange, user: VerifiedUser, session: DbSession
) -> SubjectOut:
    subjects = SubjectRepository(session, user.id)
    found = subjects.get_with_exam(subject_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subject_not_found")
    if body.exam_date is not None and body.exam_date != found[1].exam_date:
        _check_exam_date(body.exam_date, user)
    updated = subjects.update(subject_id, name=body.name, exam_date=body.exam_date)
    assert updated is not None  # found above, in the same transaction
    return _out(*updated)
