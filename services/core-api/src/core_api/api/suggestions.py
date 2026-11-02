"""`GET /v1/suggestions` and `GET /v1/subjects/{id}/suggestion` (T7.10b, US-15): what to study next,
computed from the current state on each call. Reads only; the session a suggestion opens is
recorded in the ledger by Save (T7.8). No AI, no "late", no pressure wording (AC5)."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.db.session import DbSession
from core_api.domain.suggest import EmptyReason, Suggestion, empty_text, reason_line
from core_api.services.suggestions import UnknownSubjectError, build_suggestions, suggest_one

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])


class PaceOut(BaseModel):
    remaining_leaves: int
    remaining_weight: float
    unit: str | None
    days_left: int | None
    text: str


class SuggestionOut(BaseModel):
    subject_id: uuid.UUID
    subject_name: str
    kind: Literal["next_leaf", "review_practice", "free_session"]
    section_id: uuid.UUID | None
    section_title: str | None
    partial: bool
    remaining: float | None
    unit: str | None
    reason: str
    pace: PaceOut


class EmptyOut(BaseModel):
    reason: EmptyReason
    text: str
    links: list[Literal["review", "practice"]]


class SuggestionsOut(BaseModel):
    today: date
    suggestions: list[SuggestionOut]
    finished: list[SuggestionOut]
    empty: EmptyOut | None


class SubjectSuggestionOut(BaseModel):
    today: date
    suggestion: SuggestionOut


def suggestion_out(s: Suggestion, name: str) -> SuggestionOut:
    return SuggestionOut(
        subject_id=s.subject_id,
        subject_name=name,
        kind=s.kind,
        section_id=s.leaf_id,
        section_title=s.leaf_title,
        partial=s.partial,
        remaining=s.remaining_weight,
        unit=s.unit,
        reason=reason_line(s),
        pace=PaceOut(
            remaining_leaves=s.pace.remaining_leaves,
            remaining_weight=s.pace.remaining_weight,
            unit=s.pace.unit,
            days_left=s.pace.days_left,
            text=s.pace.text,
        ),
    )


@router.get("/suggestions")
def get_suggestions(user: VerifiedUser, session: DbSession, now: Now) -> SuggestionsOut:
    result = build_suggestions(session, user, now)
    names = result.subject_names
    return SuggestionsOut(
        today=result.today,
        suggestions=[suggestion_out(s, names[s.subject_id]) for s in result.suggestions],
        finished=[suggestion_out(s, names[s.subject_id]) for s in result.finished],
        empty=None
        if result.empty is None
        else EmptyOut(
            reason=result.empty, text=empty_text(result.empty), links=["review", "practice"]
        ),
    )


@router.get("/subjects/{subject_id}/suggestion")
def get_subject_suggestion(
    subject_id: uuid.UUID, user: VerifiedUser, session: DbSession, now: Now
) -> SubjectSuggestionOut:
    try:
        today, suggestion, name = suggest_one(session, user, now, subject_id)
    except UnknownSubjectError:
        raise HTTPException(status_code=404, detail="subject_not_found") from None
    return SubjectSuggestionOut(today=today, suggestion=suggestion_out(suggestion, name))
