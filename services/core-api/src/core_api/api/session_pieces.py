"""A study session in pieces (F2, 04/11): each "Ghi lại" keeps one piece at once; "Hoàn thành"
hands every piece in as one submission, which the existing worker turns into cards (F3)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from core_api.api.deps import Now, Storage, VerifiedUser, verified_user
from core_api.api.submissions import (
    FileIn,
    MentionIn,
    SubmissionOut,
    SubmitRequest,
    Typed,
    submit,
)
from core_api.db.models import SessionPiece, Submission
from core_api.db.models.study_session import DESCRIPTION_MAX
from core_api.db.session import DbSession
from core_api.repositories.study_session import StudySessionRepository
from core_api.security.rate_limit import RateLimiter, get_rate_limiter

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

MAX_PIECES = 60


class PieceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Typed = Field(default="", max_length=DESCRIPTION_MAX)
    files: list[FileIn] = Field(default=[], max_length=20)
    mentions: list[MentionIn] = Field(default=[], max_length=20)


class PieceOut(BaseModel):
    id: uuid.UUID
    position: int
    text: str
    file_count: int
    created_at: datetime


class PiecesOut(BaseModel):
    pieces: list[PieceOut]
    submitted: bool


def _out(row: SessionPiece) -> PieceOut:
    return PieceOut(
        id=row.id,
        position=row.position,
        text=row.body,
        file_count=len(row.files),
        created_at=row.created_at,
    )


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _pieces(session: DbSession, user_id: uuid.UUID, session_id: uuid.UUID) -> list[SessionPiece]:
    return list(
        session.scalars(
            select(SessionPiece)
            .where(SessionPiece.session_id == session_id, SessionPiece.user_id == user_id)
            .order_by(SessionPiece.position)
        )
    )


@router.get("/study-sessions/{session_id}/pieces", response_model=PiecesOut)
def list_pieces(
    session_id: uuid.UUID, user: VerifiedUser, session: DbSession, response: Response
) -> PiecesOut:
    response.headers["Cache-Control"] = "no-store"
    if StudySessionRepository(session, user.id).get(session_id) is None:
        raise _error(404, "session_not_found")
    submitted = session.scalars(
        select(Submission.id).where(
            Submission.session_id == session_id, Submission.user_id == user.id
        )
    ).first()
    return PiecesOut(
        pieces=[_out(r) for r in _pieces(session, user.id, session_id)],
        submitted=submitted is not None,
    )


@router.post("/study-sessions/{session_id}/pieces", response_model=PieceOut, status_code=201)
def add_piece(
    session_id: uuid.UUID, body: PieceIn, user: VerifiedUser, session: DbSession
) -> PieceOut:
    """Keep one piece. 404 `session_not_found`; 409 `session_confirmed` (already handed in);
    422 `nothing_submitted`, `too_many_pieces`."""
    repo = StudySessionRepository(session, user.id)
    draft = repo.lock(session_id)
    if draft is None:
        raise _error(404, "session_not_found")
    if (
        draft.status != "draft"
        or session.scalars(select(Submission.id).where(Submission.session_id == session_id)).first()
    ):
        raise _error(409, "session_confirmed")
    if not body.text.strip() and not body.files:
        raise _error(422, "nothing_submitted")
    existing = _pieces(session, user.id, session_id)
    if len(existing) >= MAX_PIECES:
        raise _error(422, "too_many_pieces")
    row = SessionPiece(
        session_id=session_id,
        position=(existing[-1].position + 1) if existing else 0,
        body=body.text.strip(),
        files=[f.model_dump(mode="json") for f in body.files],
        mentions=[m.model_dump(mode="json") for m in body.mentions],
    )
    session.add(row)
    row.user_id = user.id
    session.flush()
    session.refresh(row)
    return _out(row)


@router.post(
    "/study-sessions/{session_id}/complete",
    response_model=SubmissionOut,
    status_code=201,
)
def complete(  # noqa: PLR0913
    session_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    storage: Storage,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    now: Now,
    response: Response,
) -> SubmissionOut:
    """Hand every piece in as one submission (queued for the worker). 404 `session_not_found`;
    422 `nothing_submitted`; the rest as `POST /v1/submissions`."""
    if StudySessionRepository(session, user.id).get(session_id) is None:
        raise _error(404, "session_not_found")
    rows = _pieces(session, user.id, session_id)
    if not rows:
        raise _error(422, "nothing_submitted")
    texts: list[str] = []
    mentions: list[dict[str, Any]] = []
    files: dict[str, dict[str, Any]] = {}
    offset = 0
    for row in rows:
        for m in row.mentions:
            mentions.append({**m, "start": m["start"] + offset, "end": m["end"] + offset})
        offset += len(row.body) + 2
        texts.append(row.body)
        for f in row.files:
            files.setdefault(f["sha256"], f)
    joined = "\n\n".join(t for t in texts)
    fits = [m for m in mentions if m["end"] <= DESCRIPTION_MAX]
    try:
        request = SubmitRequest.model_validate(
            {
                "session_id": session_id,
                "description": joined[:DESCRIPTION_MAX] or None,
                "text": joined if joined.strip() else None,
                "files": list(files.values()),
                "mentions": fits[:20],
            }
        )
    except ValidationError:
        raise _error(422, "text_too_long") from None
    return submit(request, user, session, storage, limiter, now, response)
