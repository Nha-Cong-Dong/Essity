"""Reviewing draft cards (T7.8, US-02b AC6-AC9, AC12): the pure rules, no database.

Shared by the review API and the command bar (T9.2). Merging and splitting are deterministic and
never call an LLM (AC6). Only draft cards can be merged, split or edited.
"""

import builtins
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core_api.db.models import (
    Anchor,
    DocSection,
    KnowledgeUnit,
    Outbox,
    SessionRange,
    StudySession,
    UnitRevision,
)
from core_api.domain.learning_day import learning_day
from core_api.messaging.outbox import current_trace_context
from core_api.repositories.study_session import StudySessionRepository
from core_api.repositories.unit import DraftRepository, UnitLineageRepository

UNDO_WINDOW = timedelta(days=7)
CHANGED_ELSEWHERE = "thẻ đã đổi ở nơi khác"


class UnitChangedElsewhere(Exception):
    """The If-Match version is not the card's current one (409)."""

    message = CHANGED_ELSEWHERE


class NotADraft(Exception):
    """Merge, split or edit asked for a card that is not a draft."""


class UndoExpired(Exception):
    """A discarded card is older than the undo window (410)."""


@dataclass(frozen=True)
class DraftCard:
    id: uuid.UUID
    session_id: uuid.UUID | None
    title: str
    content: str
    kind: str
    status: str
    version: int
    created_at: datetime
    anchor_ids: tuple[uuid.UUID, ...] = ()
    section_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class SplitPart:
    title: str
    content: str
    anchor_ids: tuple[uuid.UUID, ...]


def check_version(current: int, expected: int) -> None:
    if current != expected:
        raise UnitChangedElsewhere


def _require_drafts(cards: list[DraftCard]) -> None:
    if any(c.status != "draft" for c in cards):
        raise NotADraft


def merge(cards: list[DraftCard]) -> tuple[DraftCard, list[DraftCard]]:
    """Keep the oldest card (ties: smaller id), join the contents in that order, union anchors and
    sections. Returns the kept card (same id, content joined) and the cards that become merged."""
    if len(cards) < 2:
        raise ValueError("merge needs at least two cards")
    _require_drafts(cards)
    if len({c.session_id for c in cards}) != 1 or cards[0].session_id is None:
        raise NotADraft
    ordered = sorted(cards, key=lambda c: (c.created_at, str(c.id)))
    keep, rest = ordered[0], ordered[1:]
    kept = DraftCard(
        id=keep.id,
        session_id=keep.session_id,
        title=keep.title,
        content="\n\n".join(c.content for c in ordered),
        kind=keep.kind,
        status="draft",
        version=keep.version + 1,
        created_at=keep.created_at,
        anchor_ids=_union(c.anchor_ids for c in ordered),
        section_ids=_union(c.section_ids for c in ordered),
    )
    return kept, rest


def split(card: DraftCard, parts: list[SplitPart]) -> list[SplitPart]:
    """Check a split request: at least two parts, each with a title and content, anchors only from
    the card, each in one part (anchors not given to a part stay on the merged original). Returns
    the parts unchanged."""
    _require_drafts([card])
    if len(parts) < 2:
        raise ValueError("split needs at least two parts")
    if any(not p.title.strip() or not p.content.strip() for p in parts):
        raise ValueError("every part needs a title and content")
    used = [a for p in parts for a in p.anchor_ids]
    if len(set(used)) != len(used) or not set(used) <= set(card.anchor_ids):
        raise ValueError("anchors must come from the card, each in one part")
    return parts


def can_undo(retired_at: datetime, now: datetime) -> bool:
    return now - retired_at <= UNDO_WINDOW


def require_undo(retired_at: datetime, now: datetime) -> None:
    if not can_undo(retired_at, now):
        raise UndoExpired


def saved_learning_day(now: datetime, tz: ZoneInfo, day_start_hour: int) -> date:
    """The learning day a card is saved on; it enters review on the next one (AC12)."""
    return learning_day(now, tz, day_start_hour)


def in_review(saved_day: date, today: date) -> bool:
    return saved_day < today


def _union(groups: Iterable[tuple[uuid.UUID, ...]]) -> tuple[uuid.UUID, ...]:
    seen: dict[uuid.UUID, None] = {}
    for group in groups:
        for item in group:
            seen.setdefault(item)
    return tuple(seen)


_NOTE_EXT = "jpg|png|pdf|txt|md|docx|pptx"


def file_keys_are_own(keys: Iterable[str], user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """True when every key is `users/<user>/sessions/<session>/notes/<sha256>.<ext>` of this very
    user and session, matched whole (same shape as the submission CHECK, migration 0024)."""
    pattern = re.compile(
        rf"users/{user_id}/sessions/{session_id}/notes/[0-9a-f]{{64}}\.(?:{_NOTE_EXT})"
    )
    return all(pattern.fullmatch(k) for k in keys)


# --- Application service: the review of a session's draft cards (T7.8) ---------------------------
# Every write locks the study session first, then the cards in id order (`DraftRepository`): one
# order, so a merge, an edit and a Save of one session wait on each other and never deadlock.


class SessionNotFound(LookupError):
    """No such study session for this user."""


class UnitNotFound(LookupError):
    """No such card for this user (or not of this session)."""


class NotUndoable(Exception):
    """The card was not discarded by the learner (or by this code): nothing to undo."""


@dataclass(frozen=True)
class NewRange:
    document_id: uuid.UUID
    start_page: int
    end_page: int


@dataclass(frozen=True)
class SaveItem:
    unit_id: uuid.UUID
    version: int


@dataclass(frozen=True)
class SaveResult:
    saved: list[uuid.UUID]


@dataclass(frozen=True)
class DraftView:
    unit: KnowledgeUnit
    anchors: list[Anchor]
    revisions: list[UnitRevision]
    section_ids: list[uuid.UUID]


def revision_content(title: str, summary: str, kind: str) -> dict[str, str]:
    return {"title": title, "content": summary, "kind": kind}


def _card(unit: KnowledgeUnit, anchors: list[Anchor], sections: list[uuid.UUID]) -> DraftCard:
    return DraftCard(
        id=unit.id,
        session_id=unit.session_id,
        title=unit.title,
        content=unit.summary,
        kind=unit.kind,
        status=unit.status,
        version=unit.version,
        created_at=unit.created_at,
        anchor_ids=tuple(a.id for a in anchors),
        section_ids=tuple(sections),
    )


class UnitReviewService:
    """Nothing here commits: the caller's commit keeps it all, its rollback drops it all."""

    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.repo = DraftRepository(session, user_id)

    # reading ---------------------------------------------------------------------------------

    def drafts(self, session_id: uuid.UUID) -> "builtins.list[DraftView]":
        if StudySessionRepository(self.session, self.user_id).get(session_id) is None:
            raise SessionNotFound(session_id)
        return self._views(self.repo.drafts_of_session(session_id))

    def get(self, unit_id: uuid.UUID) -> DraftView:
        unit = self.repo.get(unit_id)
        if unit is None or unit.session_id is None:
            raise UnitNotFound(unit_id)
        return self._views([unit])[0]

    def _views(self, units: list[KnowledgeUnit]) -> list[DraftView]:
        ids = [u.id for u in units]
        if not ids:
            return []
        anchors = self.repo.anchors_of(ids)
        revisions = self.repo.revisions_of(ids)
        sections = self.repo.sections_of(ids)
        return [
            DraftView(u, anchors.get(u.id, []), revisions.get(u.id, []), sections.get(u.id, []))
            for u in units
        ]

    # locking ---------------------------------------------------------------------------------

    def _open_session(self, session_id: uuid.UUID) -> StudySession:
        study = self.repo.lock_session(session_id)
        if study is None:
            raise SessionNotFound(session_id)
        return study

    def _open_unit(self, unit_id: uuid.UUID) -> tuple[StudySession, KnowledgeUnit]:
        """The session of the card (found unlocked, then locked first) and the card locked."""
        found = self.repo.get(unit_id)
        if found is None or found.session_id is None:
            raise UnitNotFound(unit_id)
        study = self._open_session(found.session_id)
        locked = self.repo.lock_drafts(study.id, [unit_id])
        if not locked:
            raise UnitNotFound(unit_id)
        return study, locked[0]

    # writing one card ------------------------------------------------------------------------

    def edit(
        self,
        unit_id: uuid.UUID,
        expected_version: int,
        *,
        title: str | None = None,
        content: str | None = None,
        kind: str | None = None,
    ) -> KnowledgeUnit:
        _, unit = self._open_unit(unit_id)
        if unit.status != "draft":
            raise NotADraft
        check_version(unit.version, expected_version)
        if title is not None:
            unit.title = title
        if content is not None:
            unit.summary = content
        if kind is not None:
            unit.kind = kind
        unit.version += 1
        self.session.flush()
        return unit

    def discard(self, unit_id: uuid.UUID, now: datetime) -> KnowledgeUnit:
        _, unit = self._open_unit(unit_id)
        if unit.status != "draft":
            raise NotADraft
        unit.status, unit.retired_at = "retired", now
        unit.version += 1
        self.session.flush()
        return unit

    def undo(self, unit_id: uuid.UUID, now: datetime) -> KnowledgeUnit:
        """Back to draft within the window. A retired card without `retired_at` (an old row) is
        not undoable; `retired_at` goes back to NULL in the same change."""
        _, unit = self._open_unit(unit_id)
        if unit.status != "retired" or unit.retired_at is None:
            raise NotUndoable
        require_undo(unit.retired_at, now)
        unit.status, unit.retired_at = "draft", None
        unit.version += 1
        self.session.flush()
        return unit

    def add(
        self,
        session_id: uuid.UUID,
        *,
        title: str,
        content: str,
        kind: str,
        section_id: uuid.UUID | None = None,
    ) -> KnowledgeUnit:
        """A card the learner writes (AC6): no AI version, so rev 0 is theirs, and no anchor."""
        study = self._open_session(session_id)
        sections: list[uuid.UUID] = []
        if section_id is not None:
            owned = self.session.scalar(
                select(DocSection.id).where(
                    DocSection.user_id == self.user_id,
                    DocSection.subject_id == study.subject_id,
                    DocSection.id == section_id,
                )
            )
            sections = [owned] if owned is not None else []
        unit_id = self.repo.insert_draft(
            subject_id=study.subject_id,
            session_id=study.id,
            draft_key=None,
            title=title,
            summary=content,
            kind=kind,
            section_id=sections[0] if sections else None,
            run_id=uuid.uuid4(),
        )
        assert unit_id is not None
        self.repo.add_revision(unit_id, 0, "user", revision_content(title, content, kind))
        self.repo.add_sections(unit_id, study.subject_id, sections)
        unit = self.repo.get(unit_id)
        assert unit is not None
        return unit

    # merge and split -------------------------------------------------------------------------

    def merge(self, session_id: uuid.UUID, unit_ids: list[uuid.UUID]) -> KnowledgeUnit:
        study = self._open_session(session_id)
        wanted = sorted(set(unit_ids))
        locked = self.repo.lock_drafts(study.id, wanted)
        if len(locked) != len(wanted):
            raise UnitNotFound(wanted[0])
        anchors, sections = self.repo.anchors_of(wanted), self.repo.sections_of(wanted)
        cards = [_card(u, anchors.get(u.id, []), sections.get(u.id, [])) for u in locked]
        kept_card, rest = merge(cards)
        by_id = {u.id: u for u in locked}
        kept = by_id[kept_card.id]
        kept.summary = kept_card.content
        kept.version = kept_card.version
        have = set(sections.get(kept.id, []))
        extra = [s for s in kept_card.section_ids if s not in have]
        for old in rest:
            self.session.execute(
                update(Anchor)
                .where(Anchor.user_id == self.user_id, Anchor.unit_id == old.id)
                .values(unit_id=kept.id)
            )
            by_id[old.id].status = "merged"
            by_id[old.id].version += 1
        self.session.flush()
        self.repo.add_sections(kept.id, kept.subject_id, extra)
        lineage = UnitLineageRepository(self.session, self.user_id)
        for old in rest:
            lineage.create(old.id, kept.id, kept.run_id)
        return kept

    def split(
        self, unit_id: uuid.UUID, expected_version: int, parts: list[SplitPart]
    ) -> list[KnowledgeUnit]:
        """Into new draft cards: the part's anchors move to it, the sections are copied, the
        original becomes `merged` (it went into the parts, `unit_lineage` says where)."""
        study, unit = self._open_unit(unit_id)
        if unit.status != "draft":
            raise NotADraft
        check_version(unit.version, expected_version)
        anchors, sections = self.repo.anchors_of([unit.id]), self.repo.sections_of([unit.id])
        card = _card(unit, anchors.get(unit.id, []), sections.get(unit.id, []))
        checked = split(card, parts)
        lineage = UnitLineageRepository(self.session, self.user_id)
        made: list[KnowledgeUnit] = []
        for part in checked:
            new_id = self.repo.insert_draft(
                subject_id=unit.subject_id,
                session_id=study.id,
                draft_key=None,
                title=part.title,
                summary=part.content,
                kind=unit.kind,
                section_id=unit.section_id,
                run_id=unit.run_id,
            )
            assert new_id is not None
            self.repo.add_revision(
                new_id, 0, "user", revision_content(part.title, part.content, unit.kind)
            )
            self.repo.add_sections(new_id, unit.subject_id, sections.get(unit.id, []))
            if part.anchor_ids:
                self.session.execute(
                    update(Anchor)
                    .where(Anchor.user_id == self.user_id, Anchor.id.in_(part.anchor_ids))
                    .values(unit_id=new_id)
                )
            lineage.create(unit.id, new_id, unit.run_id)
            new = self.repo.get(new_id)
            assert new is not None
            made.append(new)
        unit.status = "merged"
        unit.version += 1
        self.session.flush()
        return made

    # Save ------------------------------------------------------------------------------------

    def save(
        self,
        session_id: uuid.UUID,
        items: list[SaveItem],
        *,
        now: datetime,
        tz: ZoneInfo,
        day_start_hour: int,
        ranges: list[NewRange],
    ) -> SaveResult:
        """The cards the learner saw become cards (AC9), in the caller's one transaction: status
        canonical, revision 1 (the learner's), ledger, ranges, one `unit.saved.v1` each.

        A card already saved is skipped (a second click saves nothing: `saved == []`); a card
        whose version is not the one seen raises `UnitChangedElsewhere`; a card of the list that
        is not a card of this session raises `UnitNotFound`; drafts not in the list stay drafts.
        """
        study = self._open_session(session_id)
        wanted = sorted({i.unit_id for i in items})
        locked = {u.id: u for u in self.repo.lock_drafts(study.id, wanted)}
        if set(locked) != set(wanted):
            raise UnitNotFound(next(i for i in wanted if i not in locked))
        versions = {i.unit_id: i.version for i in items}
        to_save: list[KnowledgeUnit] = []
        for unit_id in wanted:
            unit = locked[unit_id]
            if unit.status == "canonical" and unit.saved_at is not None:
                continue
            if unit.status != "draft":
                raise NotADraft
            check_version(unit.version, versions[unit_id])
            to_save.append(unit)
        if not to_save:
            return SaveResult(saved=[])
        day = saved_learning_day(now, tz, day_start_hour)
        existing = self.repo.revisions_of([u.id for u in to_save])
        per_section: dict[uuid.UUID | None, int] = {}
        for unit in to_save:
            rev = max((r.rev for r in existing.get(unit.id, [])), default=-1) + 1
            unit.status, unit.saved_at, unit.saved_learning_day = "canonical", now, day
            unit.retired_at = None
            unit.version += 1
            self.session.flush()
            self.repo.add_revision(
                unit.id, rev, "user", revision_content(unit.title, unit.summary, unit.kind)
            )
            per_section[unit.section_id] = per_section.get(unit.section_id, 0) + 1
            _enqueue_unit_saved(self.session, self.user_id, unit, rev, now)
        for section_id, count in per_section.items():
            self.repo.ledger_add(
                subject_id=study.subject_id,
                session_id=study.id,
                learning_day=day,
                section_id=section_id,
                count=count,
            )
        self._add_ranges(study.id, ranges)
        return SaveResult(saved=[u.id for u in to_save])

    def _add_ranges(self, session_id: uuid.UUID, ranges: list[NewRange]) -> None:
        have = StudySessionRepository(self.session, self.user_id).ranges_of(session_id)
        known = {(r.document_id, r.start_page, r.end_page) for r in have}
        position = max((r.position for r in have), default=-1) + 1
        for item in ranges:
            key = (item.document_id, item.start_page, item.end_page)
            if key in known:
                continue
            known.add(key)
            self.session.add(
                SessionRange(
                    user_id=self.user_id,
                    session_id=session_id,
                    document_id=item.document_id,
                    start_page=item.start_page,
                    end_page=item.end_page,
                    depth="unclear",
                    position=position,
                )
            )
            position += 1
        self.session.flush()


def _enqueue_unit_saved(
    session: Session, user_id: uuid.UUID, unit: KnowledgeUnit, rev: int, now: datetime
) -> None:
    """One `unit.saved.v1` row in the outbox, in the caller's transaction (ARCH 7.3: unit_id,
    unit_rev, subject_id). The contract file and the envelope model come with T7.8b; until then
    the row is written directly and nothing relays it to a consumer that exists."""
    trace = current_trace_context().model_dump()
    session.add(
        Outbox(
            id=uuid.uuid4(),
            user_id=user_id,
            event_type="unit.saved.v1",
            payload={
                "unit_id": str(unit.id),
                "unit_rev": rev,
                "subject_id": str(unit.subject_id),
            },
            trace_context={k: v for k, v in trace.items() if v is not None},
            occurred_at=now,
            available_at=now,
        )
    )
    session.flush()
