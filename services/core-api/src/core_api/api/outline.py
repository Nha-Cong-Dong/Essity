"""The outline of a subject's main textbook and its edits (T7.4, US-13 AC4-AC6, US-01 AC5).

- `GET /v1/subjects/{id}/outline`: the tree with `weight`, `unit`, `source`, studied state and
  the subject's progress. No main textbook (or none read yet) is a 200 with `reason`, so the
  screen can say why "what to study next" is empty (US-13 AC8).
- `PATCH /v1/sections/{id}`: page range (`page_start` and `page_end` together), `excluded`,
  `studied`. The answer is the whole outline: an edit moves the weights above it.
- `PUT /v1/subjects/{id}/textbook`: set or change the main textbook.

The edits are `OutlineService` methods, so the command bar (T9.2) reuses them. Nothing here
logs a title or a name.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt

from core_api.api.deps import VerifiedUser, verified_user
from core_api.db.models import DocSection, Document
from core_api.db.session import DbSession
from core_api.services.outline import (
    DocumentNotFoundError,
    NoChangeError,
    OutlineService,
    OutlineView,
    RangeError,
    SectionNotFoundError,
    SubjectNotFoundError,
    TextbookHasCardsError,
    TextbookNotReadyError,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

Reason = Literal["no_textbook", "not_indexed", "no_outline"]
Unit = Literal["page", "slide", "est_page"]


class SectionOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    title: str
    page_start: int
    page_end: int
    weight: float
    unit: Unit
    source: Literal["bookmark", "heading", "llm_toc", "chunk10", "user"]
    # The learner's own flag; `excluded_effective` also holds for a section under an excluded one.
    excluded: bool
    excluded_effective: bool
    # Covered share of the section's weight (leaves not excluded under it), 0..1.
    progress: float
    studied: bool
    children: list["SectionOut"]


class OutlineDocumentOut(BaseModel):
    id: uuid.UUID
    short_name: str
    page_count: int | None


class OutlineOut(BaseModel):
    subject_id: uuid.UUID
    document: OutlineDocumentOut | None
    reason: Reason | None
    # Share of the weight of the leaves not excluded that is covered (US-13 AC5).
    progress: float
    # Every section is a stand-in (blocks of ten pages) until the learner fixes the outline.
    temporary: bool
    sections: list[SectionOut]


class SectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_start: StrictInt | None = None
    page_end: StrictInt | None = None
    excluded: StrictBool | None = None
    studied: StrictBool | None = None


class TextbookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID
    # The learner has seen what replacing the textbook does (the confirmation of DESIGN §6.4).
    confirm: StrictBool = False


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _tree(view: OutlineView) -> list[SectionOut]:
    nodes: dict[uuid.UUID, SectionOut] = {}
    roots: list[SectionOut] = []
    for section in view.sections:  # parents come before their children
        progress = view.section_progress.get(section.id, 0.0)
        node = SectionOut(
            id=section.id,
            parent_id=section.parent_id,
            title=section.title,
            page_start=section.page_start,
            page_end=section.page_end,
            weight=section.weight,
            unit=section.unit,  # pyright: ignore[reportArgumentType]
            source=section.source,  # pyright: ignore[reportArgumentType]
            excluded=section.excluded,
            excluded_effective=section.id in view.excluded,
            progress=progress,
            studied=section.weight > 0 and progress >= 1.0,
            children=[],
        )
        nodes[section.id] = node
        (nodes[section.parent_id].children if section.parent_id else roots).append(node)
    return roots


def _reason(document: Document | None, sections: list[DocSection]) -> Reason | None:
    if document is None:
        return "no_textbook"
    if document.status != "indexed":
        return "not_indexed"
    return None if sections else "no_outline"


def outline_out(subject_id: uuid.UUID, view: OutlineView) -> OutlineOut:
    document = view.document
    return OutlineOut(
        subject_id=subject_id,
        document=None
        if document is None
        else OutlineDocumentOut(
            id=document.id, short_name=document.short_name, page_count=document.page_count
        ),
        reason=_reason(document, view.sections),
        progress=view.progress,
        temporary=bool(view.sections) and all(s.source == "chunk10" for s in view.sections),
        sections=_tree(view),
    )


@router.get("/subjects/{subject_id}/outline", response_model=OutlineOut)
def read_outline(
    subject_id: uuid.UUID, user: VerifiedUser, session: DbSession, response: Response
) -> OutlineOut:
    """The outline of the subject's main textbook. Errors: 404 `subject_not_found` (another
    user's too)."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return outline_out(subject_id, OutlineService(session, user.id).view(subject_id))
    except SubjectNotFoundError:
        raise _error(404, "subject_not_found") from None


@router.patch(
    "/sections/{section_id}",
    response_model=OutlineOut,
    responses={422: {"description": "The range breaks a rule"}},
)
def patch_section(
    section_id: uuid.UUID,
    body: SectionPatch,
    user: VerifiedUser,
    session: DbSession,
    response: Response,
) -> OutlineOut:
    """Change a section's page range, `excluded` or `studied` (US-13 AC4). Errors: 404
    `section_not_found` (another user's too); 422 `nothing_to_change`, `invalid_range`
    (`0 < start <= end`, both ends or neither), `outside_document`, `outside_parent`,
    `children_outside`."""
    response.headers["Cache-Control"] = "no-store"
    service = OutlineService(session, user.id)
    try:
        section = service.edit_section(
            section_id,
            page_start=body.page_start,
            page_end=body.page_end,
            excluded=body.excluded,
            studied=body.studied,
        )
        return outline_out(section.subject_id, service.view(section.subject_id))
    except SectionNotFoundError:
        raise _error(404, "section_not_found") from None
    except SubjectNotFoundError:
        raise _error(404, "section_not_found") from None
    except NoChangeError:
        raise _error(422, "nothing_to_change") from None
    except RangeError as error:
        raise _error(422, error.code) from None


@router.put(
    "/subjects/{subject_id}/textbook",
    response_model=OutlineOut,
    responses={409: {"description": "The textbook has cards linked to it; confirm to change it"}},
)
def put_textbook(
    subject_id: uuid.UUID,
    body: TextbookIn,
    user: VerifiedUser,
    session: DbSession,
    response: Response,
) -> OutlineOut | JSONResponse:
    """Set or change the subject's main textbook (US-01 AC5). The old one becomes `auxiliary`;
    nothing is deleted. Errors: 404 `subject_not_found`, `document_not_found` (another subject's
    or user's too); 409 `document_not_ready` (not uploaded, refused or failed), or
    `textbook_has_cards` with `cards`: live cards are linked to the current textbook, send
    `confirm: true` after the learner has agreed."""
    response.headers["Cache-Control"] = "no-store"
    service = OutlineService(session, user.id)
    try:
        service.set_textbook(subject_id, body.document_id, confirm=body.confirm)
        return outline_out(subject_id, service.view(subject_id))
    except SubjectNotFoundError:
        raise _error(404, "subject_not_found") from None
    except DocumentNotFoundError:
        raise _error(404, "document_not_found") from None
    except TextbookNotReadyError:
        raise _error(409, "document_not_ready") from None
    except TextbookHasCardsError as error:
        return JSONResponse({"detail": "textbook_has_cards", "cards": error.cards}, status_code=409)
