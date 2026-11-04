"""Move the draft cards that were waiting for review into the vault (CARDS-V3).

Before CARDS-V3 a result's cards were drafts the learner confirmed on a review screen; now they go
straight to the vault and the screen is gone, so a draft left over would never be seen again. This
runs once, by hand (`python -m core_api.cli promote-drafts`), and again without harm: it takes only
cards still in the `draft` status, so a card already promoted, edited, merged or retired is left
alone, and a retired card never comes back.

It is not SQL: it calls `UnitReviewService.promote`, the door a Save uses, so each card gets the
learner's revision, its ledger row, its `unit.saved.v1` event, its review question and edge jobs,
in the same transaction (ADR-0018). The learning day is that of the user's own timezone and day
start. Run `--dry-run` first to see the counts; the move cannot be undone (back up first,
ADR-0012).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.db.models import Anchor, KnowledgeUnit, User
from core_api.domain.unit_review import NewRange, UnitReviewService


@dataclass(frozen=True)
class PromoteReport:
    users: int
    sessions: int
    cards: int


def _ranges(session: Session, user_id: uuid.UUID, unit_ids: list[uuid.UUID]) -> list[NewRange]:
    pages: dict[uuid.UUID, tuple[int, int]] = {}
    rows = session.execute(
        select(Anchor.document_id, Anchor.page_no).where(
            Anchor.user_id == user_id, Anchor.unit_id.in_(unit_ids), Anchor.page_no.is_not(None)
        )
    )
    for document_id, page in rows:
        if document_id is None or page is None:
            continue
        low, high = pages.get(document_id, (page, page))
        pages[document_id] = (min(low, page), max(high, page))
    return [NewRange(d, lo, hi) for d, (lo, hi) in pages.items()]


def promote_drafts(session: Session, *, now: datetime, dry_run: bool = False) -> PromoteReport:
    """Promote every draft card of every session. The caller commits (or rolls back)."""
    waiting = session.execute(
        select(KnowledgeUnit.user_id, KnowledgeUnit.session_id)
        .where(KnowledgeUnit.status == "draft", KnowledgeUnit.session_id.is_not(None))
        .distinct()
        .order_by(KnowledgeUnit.user_id, KnowledgeUnit.session_id)
    ).all()
    users: set[uuid.UUID] = set()
    sessions = cards = 0
    for user_id, session_id in waiting:
        if session_id is None:
            continue
        user = session.get(User, user_id)
        if user is None:
            continue
        review = UnitReviewService(session, user_id)
        study = review.repo.lock_session(session_id)
        if study is None:
            continue
        drafts = [u for u in review.repo.lock_drafts(session_id) if u.status == "draft"]
        if not drafts:
            continue
        users.add(user_id)
        sessions += 1
        cards += len(drafts)
        if dry_run:
            continue
        # Each card is saved at the moment it was made (never later than `now`), so the old
        # cards enter review on the days they would have, not all on one.
        ranges = _ranges(session, user_id, [u.id for u in drafts])
        for unit in drafts:
            review.promote(
                study,
                [unit],
                now=min(now, unit.created_at),
                tz=ZoneInfo(user.timezone),
                day_start_hour=user.day_start_hour,
                ranges=ranges,
            )
    return PromoteReport(users=len(users), sessions=sessions, cards=cards)
