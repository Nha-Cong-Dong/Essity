"""`/v1/subjects`: a subject with its exam date (US-01, T1.19).

Created with exactly two fields, name and exam date (AC1). The exam date must be after the
user's current learning day (AC2): an exam today is refused. A subject whose exam is over can
still be renamed: PATCH checks the date only when it changes. Someone else's subject, a deleted
one and one that never existed all answer the same 404. DELETE hides a subject with no review
history (T2.3b).
"""

import unicodedata
import uuid
from datetime import date, datetime
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

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.text import has_control, is_unicode
from core_api.db.models import Exam, Subject, User
from core_api.db.session import DbSession
from core_api.domain.subjects import (
    ExamDateNotInFutureError,
    ExamDateTooFarError,
    days_until_exam,
    normalize_subject_name,
    validate_exam_date,
)
from core_api.repositories.subject import (
    SubjectHasHistoryError,
    SubjectNotFoundError,
    SubjectRepository,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

NAME_MAX = 200  # subject.name is String(200)
INVISIBLE = {"Cf", "Zs", "Zl", "Zp"}  # format characters and separators


def _name(value: str) -> str:
    # JSON can carry a lone surrogate (a "\ud800" escape): Python holds it, UTF-8 cannot store it.
    if not is_unicode(value):
        raise ValueError("name must be valid Unicode text")
    value = normalize_subject_name(value)
    # Control characters left after stripping (`api/text.py`), so a trailing newline still goes.
    if has_control(value):
        raise ValueError("name cannot contain control characters")
    # Only invisible characters (zero-width, BOM, spaces) would list as a blank subject.
    if all(unicodedata.category(c) in INVISIBLE for c in value):
        raise ValueError(f"name must be 1 to {NAME_MAX} characters")
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
    # "còn N ngày" (DESIGN §6.8), in the user's learning days (T1.20 plan K3).
    days_until_exam: int
    created_at: datetime


class ListedSubject(SubjectOut):
    # Whether the subject has an attempt, a draft included: web hides its delete button
    # (us-01 AC8, T2.3b plan F2). Only the list carries it; creating or renaming cannot change it.
    has_history: bool


def _out(subject: Subject, exam: Exam, user: User, now: datetime) -> SubjectOut:
    return SubjectOut(
        id=subject.id,
        name=subject.name,
        exam_date=exam.exam_date,
        days_until_exam=days_until_exam(
            exam.exam_date, now, ZoneInfo(user.timezone), user.day_start_hour
        ),
        created_at=subject.created_at,
    )


def _check_exam_date(exam_date: date, user: User, now: datetime) -> None:
    try:
        validate_exam_date(exam_date, now, ZoneInfo(user.timezone), user.day_start_hour)
    except ExamDateNotInFutureError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="exam_date_not_in_future"
        ) from None
    except ExamDateTooFarError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="exam_date_too_far"
        ) from None


@router.post("/subjects", status_code=status.HTTP_201_CREATED)
def create_subject(body: SubjectIn, user: VerifiedUser, session: DbSession, now: Now) -> SubjectOut:
    # One "today" per request, for the check and the answer.
    _check_exam_date(body.exam_date, user, now)
    subject, exam = SubjectRepository(session, user.id).create_with_exam(body.name, body.exam_date)
    return _out(subject, exam, user, now)


@router.get("/subjects")
def list_subjects(user: VerifiedUser, session: DbSession, now: Now) -> list[ListedSubject]:
    listed = SubjectRepository(session, user.id).list_with_exams()
    return [
        ListedSubject(**_out(s, e, user, now).model_dump(), has_history=history)
        for s, e, history in listed
    ]


@router.patch("/subjects/{subject_id}")
def change_subject(
    subject_id: uuid.UUID, body: SubjectChange, user: VerifiedUser, session: DbSession, now: Now
) -> SubjectOut:
    subjects = SubjectRepository(session, user.id)
    # Locked at the first read (T2.3b plan F10): a delete in flight is waited for, then 404.
    found = subjects.get_with_exam(subject_id, lock=True)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subject_not_found")
    if body.exam_date is not None and body.exam_date != found[1].exam_date:
        _check_exam_date(body.exam_date, user, now)
    updated = subjects.update(subject_id, name=body.name, exam_date=body.exam_date)
    if updated is None:  # cannot happen while the lock above is held; 404 rather than 500
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subject_not_found")
    return _out(*updated, user, now)


@router.delete("/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: uuid.UUID, user: VerifiedUser, session: DbSession, now: Now) -> None:
    """Soft-delete a subject with no review history (us-01 AC8, T2.3b). Its exam, questions and
    units stay but are hidden; the name can be used again. A subject with an attempt, a draft
    included, answers 409 (deleting those comes with T6.3)."""
    try:
        SubjectRepository(session, user.id).soft_delete(subject_id, now)
    except SubjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="subject_not_found"
        ) from None
    except SubjectHasHistoryError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="subject_has_history"
        ) from None
