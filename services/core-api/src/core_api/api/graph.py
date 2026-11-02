"""`GET /v1/subjects/{id}/graph` (T9.10, US-19 AC3-AC4): the data of the graph screen. A read:
nothing here changes an edge (the command bar of T9.2 does). No card or quote is logged."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core_api.api.deps import VerifiedUser, verified_user
from core_api.db.session import DbSession
from core_api.repositories.subject import SubjectRepository
from core_api.services.unit_edges import UnknownSectionError, subject_graph

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

EdgeKindOut = Literal["prerequisite", "part_of", "example_of", "contrast", "applies_to"]


class GraphSectionOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    title: str


class GraphAnchorOut(BaseModel):
    id: uuid.UUID
    document_name: str | None  # None: a note
    page_no: int | None
    quote: str


class GraphCardOut(BaseModel):
    id: uuid.UUID
    title: str
    summary: str
    section_id: uuid.UUID | None  # the card's own place; None: in no section
    anchors: list[GraphAnchorOut]
    needed_by: list[str]  # prompts of the questions that need this card


class GraphEvidenceOut(BaseModel):
    unit_id: uuid.UUID
    quote: str


class GraphEdgeOut(BaseModel):
    id: uuid.UUID
    kind: EdgeKindOut
    from_id: uuid.UUID
    to_id: uuid.UUID
    evidence: list[GraphEvidenceOut]  # empty only for an edge the learner added


class GraphOut(BaseModel):
    sections: list[GraphSectionOut]
    cards: list[GraphCardOut]
    edges: list[GraphEdgeOut]
    hidden: int  # cards left out because of the 300 cap
    truncated: bool


@router.get("/subjects/{subject_id}/graph")
def get_graph(
    subject_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    section_id: uuid.UUID | None = None,
) -> GraphOut:
    if SubjectRepository(session, user.id).get(subject_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "subject_not_found")
    try:
        graph = subject_graph(session, user.id, subject_id, section_id)
    except UnknownSectionError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "section_not_found") from error
    return GraphOut(
        sections=[
            GraphSectionOut(id=s.id, parent_id=s.parent_id, title=s.title) for s in graph.sections
        ],
        cards=[
            GraphCardOut(
                id=c.id,
                title=c.title,
                summary=c.summary,
                section_id=c.section_id,
                anchors=[
                    GraphAnchorOut(id=i, document_name=n, page_no=p, quote=q)
                    for i, n, p, q in c.anchors
                ],
                needed_by=c.needed_by,
            )
            for c in graph.cards
        ],
        edges=[
            GraphEdgeOut(
                id=e.id,
                kind=e.kind,  # pyright: ignore[reportArgumentType]
                from_id=e.src,
                to_id=e.dst,
                evidence=[
                    GraphEvidenceOut(unit_id=uuid.UUID(q["unit_id"]), quote=q["quote"])
                    for q in e.evidence
                ],
            )
            for e in graph.edges
        ],
        hidden=graph.hidden,
        truncated=graph.hidden > 0,
    )
