"""`/v1/baseline`: where the user started (US-11, T1.17).

Entered once (`POST`), editable for 7 days (`PUT`), then locked. "Later" on the screen is
`POST /v1/baseline/skip`: asked once more, then never (AC2). The server sets `entered_at` and
`is_late`; a body naming them is refused. GPA is personal data: it never reaches the logs, and a
422 never echoes it (api/errors.py).
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Self

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from core_api.api.deps import VerifiedUser, verified_user
from core_api.db.models import Baseline
from core_api.db.session import DbSession
from core_api.domain.baseline import editable_until, is_late, is_locked, needs_baseline
from core_api.repositories.baseline import BaselineRepository
from core_api.repositories.user import UserRepository

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

# GPA on a 4-point scale with at most two decimals, written with a dot: web turns "2,85" into
# "2.85" before sending (plan B7). Never rounded: a quietly changed baseline is what AC5 guards.
Gpa = Annotated[Decimal, Field(ge=0, le=4, max_digits=3, decimal_places=2, allow_inf_nan=False)]
PriorReadyDays = Annotated[int, Field(ge=0, le=365, strict=True)]


class BaselineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gpa_before: Gpa
    # Required unless "don't remember": a missing count must not pass for "0 days".
    prior_ready_days: PriorReadyDays | None = None
    # "Don't remember": stored as an estimate of 0 days (AC1).
    prior_days_unknown: StrictBool = False

    @model_validator(mode="after")
    def days_or_unknown(self) -> Self:
        if self.prior_days_unknown:
            if self.prior_ready_days not in (None, 0):
                raise ValueError("prior_ready_days must be 0 or absent when prior_days_unknown")
        elif self.prior_ready_days is None:
            raise ValueError("prior_ready_days is required unless prior_days_unknown")
        return self

    @property
    def days(self) -> int:
        return self.prior_ready_days or 0


class BaselineOut(BaseModel):
    gpa_before: Decimal
    prior_ready_days: int
    prior_days_unknown: bool
    entered_at: datetime
    is_late: bool
    locked: bool
    editable_until: datetime


class SkipOut(BaseModel):
    needs_baseline: bool


def _out(row: Baseline, now: datetime) -> BaselineOut:
    return BaselineOut(
        gpa_before=row.gpa_before,
        prior_ready_days=row.prior_ready_days,
        prior_days_unknown=row.prior_days_unknown,
        entered_at=row.entered_at,
        is_late=row.is_late,
        locked=is_locked(row.entered_at, now),
        editable_until=editable_until(row.entered_at),
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="baseline_not_found")


@router.post("/baseline", status_code=status.HTTP_201_CREATED)
def create_baseline(body: BaselineIn, user: VerifiedUser, session: DbSession) -> BaselineOut:
    now = datetime.now(UTC)
    assert user.email_verified_at is not None  # verified_user
    row = BaselineRepository(session, user.id).create(
        gpa_before=body.gpa_before,
        prior_ready_days=body.days,
        prior_days_unknown=body.prior_days_unknown,
        is_late=is_late(now, user.email_verified_at),
        now=now,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="baseline_already_exists")
    return _out(row, now)


@router.get("/baseline")
def get_baseline(user: VerifiedUser, session: DbSession, response: Response) -> BaselineOut:
    response.headers["Cache-Control"] = "no-store"
    row = BaselineRepository(session, user.id).get_mine()
    if row is None:
        raise _not_found()
    return _out(row, datetime.now(UTC))


@router.put("/baseline")
def replace_baseline(body: BaselineIn, user: VerifiedUser, session: DbSession) -> BaselineOut:
    now = datetime.now(UTC)
    baselines = BaselineRepository(session, user.id)
    row = baselines.replace(
        gpa_before=body.gpa_before,
        prior_ready_days=body.days,
        prior_days_unknown=body.prior_days_unknown,
        now=now,
    )
    if row is not None:
        return _out(row, now)
    if baselines.get_mine() is None:
        raise _not_found()
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="baseline_locked")


@router.post("/baseline/skip")
def skip_baseline(user: VerifiedUser, session: DbSession) -> SkipOut:
    if BaselineRepository(session, user.id).get_mine() is not None:
        return SkipOut(needs_baseline=False)
    skips = UserRepository(session).record_baseline_skip(user.id)
    return SkipOut(needs_baseline=needs_baseline(verified=True, has_baseline=False, skips=skips))
