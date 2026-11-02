"""The `propose_unit_edges` job (T9.9, US-19 AC2): propose the edges of one saved card. Save
enqueues it for every card it saves, next to the review question. Delivery is at least once and
`services.unit_edges.propose_edges_for_unit` is idempotent. ai-service unreachable raises, so the
job is retried; the cap or a model that broke its rules ends the job without error."""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from core_api.clients.ai_client import AiServiceClient
from core_api.config import get_settings
from core_api.db.engine import get_engine
from core_api.jobs.handler import job_handler
from core_api.jobs.queue import enqueue_job
from core_api.services.unit_edges import ProposeEdgesAi, propose_edges_for_unit

PROPOSE_UNIT_EDGES = "propose_unit_edges"

_log = logging.getLogger("core_api.jobs")


def enqueue_edge_proposal(session: Session, user_id: uuid.UUID, unit_id: uuid.UUID) -> None:
    """Add the job in the caller's transaction."""
    enqueue_job(session, PROPOSE_UNIT_EDGES, {"user_id": str(user_id), "unit_id": str(unit_id)})


def run(payload: dict[str, Any], ai: ProposeEdgesAi) -> str:
    user_id, unit_id = uuid.UUID(payload["user_id"]), uuid.UUID(payload["unit_id"])
    with Session(get_engine()) as session:
        outcome = propose_edges_for_unit(session, user_id, unit_id, ai)
        session.commit()
    return outcome


@job_handler(PROPOSE_UNIT_EDGES)
def propose_unit_edges(payload: dict[str, Any]) -> None:
    client = AiServiceClient.from_settings(get_settings())
    try:
        outcome = run(payload, client)
    finally:
        client.close()
    _log.info("edge job done", extra={"outcome": outcome})
