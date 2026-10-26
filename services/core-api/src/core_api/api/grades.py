"""`POST /v1/grades/{id}/override` and `POST /v1/questions/{id}/drop` (T2.18, US-09): "Chấm sai"
and "Bỏ câu này". The writing is `core_api.overriding`; the answer is the attempt as the result
screen shows it (`attempt_view`), now with the override as its current grade."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

from core_api.api.attempts import AttemptView, attempt_view
from core_api.api.deps import VerifiedUser, verified_user
from core_api.db.session import DbSession
from core_api.grading import GradingOutcome
from core_api.overriding import (
    GradeBusyError,
    GradeNotCurrentError,
    GradeNotFoundError,
    override_grade,
)
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import AttemptRepository
from core_api.repositories.subject import SubjectNotFoundError
from core_api.repositories.unit import UnitNotFoundError

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])


class OverrideIn(BaseModel):
    """ "Thực ra tôi đúng" is `correct`, "Thực ra tôi sai" is `incorrect` (US-09 AC1)."""

    model_config = ConfigDict(extra="forbid")
    verdict: Literal["correct", "incorrect"]


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


@router.post("/grades/{grade_id}/override")
def override(
    grade_id: uuid.UUID, body: OverrideIn, user: VerifiedUser, session: DbSession
) -> AttemptView:
    try:
        grade = override_grade(session, user, grade_id, body.verdict)
    except GradeNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "grade_not_found") from error
    except (SubjectNotFoundError, UnitNotFoundError) as error:
        raise _error(status.HTTP_404_NOT_FOUND, "subject_deleted") from error
    except GradeNotCurrentError as error:
        raise _error(status.HTTP_409_CONFLICT, "grade_not_current") from error
    except GradeBusyError as error:
        raise _error(status.HTTP_409_CONFLICT, "grading_in_progress") from error
    attempt = AttemptRepository(session, user.id).get(grade.attempt_id)
    assert attempt is not None
    return attempt_view(session, user.id, attempt, GradingOutcome("graded", grade=grade))


@router.post("/questions/{question_id}/drop", status_code=status.HTTP_204_NO_CONTENT)
def drop_question(question_id: uuid.UUID, user: VerifiedUser, session: DbSession) -> Response:
    if not QuestionRepository(session, user.id).retire(question_id):
        raise _error(status.HTTP_404_NOT_FOUND, "question_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
