"""`GET /v1/export.csv` (T9.4b, US-10 AC3/AC4): the caller's own numbers as CSV, including hours
per week. A sitting left open counts hours to its last submitted answer."""

from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.db.session import DbSession
from core_api.domain.learning_day import learning_day
from core_api.repositories.stats import ExportRepository

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])


@router.get("/export.csv")
def export_csv(user: VerifiedUser, session: DbSession, now: Now) -> Response:
    today = learning_day(now, ZoneInfo(user.timezone), user.day_start_hour)
    body = ExportRepository(session, user.id).export_csv(now, today)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="essity.csv"'},
    )
