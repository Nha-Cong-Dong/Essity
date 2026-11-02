"""Apply a typed command to the learner's data (T9.2c, ADR-0030, US-18 AC4/AC8/AC9).

`CommandService.apply` takes the command's client id, the screen session and the request (a line
of text, or ops already parsed), and in ONE transaction runs the ops through the pure domain
(`domain/commands`), writes the result with the services and repositories the screens use
(`OutlineService`, `UnitReviewService`, `practice.remove`, `StudyFilterRepository`) and logs the
command with its inverse. The command's own writes are never committed here: the caller's commit
keeps them, its rollback drops them (a failing op rolls back the savepoint of the command: no
change, no log row). The one commit is before the parser call and closes a read-only transaction:
the caller must not have written anything yet.

Order of things (plan T9.2c):
1. `payload_hash` of the request as received; a stored row of (user, command_id) answers a retry
   without calling the parser (same hash) or is refused (`CommandIdReused`).
2. The parser runs OUTSIDE the transaction (the read of step 1 is closed first).
3. One validator for the ops of the client and of the LLM; then one advisory lock on the command
   id, the object locks in the common order (`LockTargets.acquire`), the snapshot, every id
   checked against this user, the domain run, the writes, the read-back of every revision, and
   `INSERT ... ON CONFLICT DO NOTHING` (0 rows: a twin won, roll back and answer with its row).

What a log line, a trace or `CommandRejected.detail` may hold: ids, counts, op kinds and error
codes. The text of the command and the diff live in `command_log` and in the owner's response.
"""

import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models import CommandLog, DocSection, KnowledgeUnit, Question
from core_api.domain import outline as rules
from core_api.domain.commands.inverse import Change, diff
from core_api.domain.commands.registry import (
    CardAdd,
    CardAddIdea,
    CardDiscardDraft,
    CardEdit,
    CardMerge,
    CardSplit,
    CommandRejected,
    Op,
    QuestionRemoveFromPractice,
    QuestionSetAnswer,
    QuestionSetType,
    SectionExclude,
    SectionMark,
    SuggestDeferSubject,
    SuggestOnlySubject,
    kind_of,
    run_op,
)
from core_api.domain.commands.state import (
    Card,
    CardStatus,
    Document,
    Record,
    Section,
    Snapshot,
    StudyFilter,
    Subject,
)
from core_api.domain.commands.state import Question as QuestionRecord
from core_api.domain.commands.state import QuestionType as QuestionTypeRecord
from core_api.domain.unit_review import (
    NotADraft,
    SessionNotFound,
    UnitChangedElsewhere,
    UnitNotFound,
    UnitReviewService,
    revision_content,
)
from core_api.repositories.command_log import CommandLogRepository
from core_api.repositories.doc_section import DocSectionRepository
from core_api.repositories.document import DocumentRepository
from core_api.repositories.practice_removal import PracticeRemovalRepository
from core_api.repositories.practice_types import PracticeTypeRepository
from core_api.repositories.question import QuestionNotFoundError, QuestionRepository
from core_api.repositories.study_filter import StudyFilterRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import (
    DraftRepository,
    KnowledgeUnitRepository,
    UnitLineageRepository,
)
from core_api.services import practice
from core_api.services.command_codec import op_to_json, payload_hash, record_to_json, validate_ops
from core_api.services.outline import (
    NoChangeError,
    OutlineService,
    RangeError,
    SectionNotFoundError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ApplyOutcome",
    "CommandIdReused",
    "CommandRejected",
    "CommandRequest",
    "CommandService",
    "LockTargets",
]

type Parser = Callable[[str], Sequence[Mapping[str, Any]]]
type Entry = dict[str, Any]


class CommandIdReused(Exception):
    """The `command_id` is this user's, but its stored command came from another request (409)."""


@dataclass(frozen=True)
class CommandRequest:
    """What the client sent: a line of text for the parser, or the ops it parsed itself."""

    raw_text: str
    ops: Sequence[Mapping[str, Any]] | None = None


@dataclass(frozen=True)
class ApplyOutcome:
    command_id: uuid.UUID
    status: str  # applied | undone (a retry of a command undone since)
    diff: list[dict[str, Any]]  # one item per changed object: kind, id, verb, before, after
    affected: int
    op_kinds: list[str]
    replayed: bool = False


class _Raced(Exception):
    """A twin of this command inserted its row first: roll back and answer with it."""


@dataclass
class LockTargets:
    """The rows a command (or its undo) is about to write, locked in ONE order for apply and undo
    alike: command, then document < doc_section < question < study_filter < study_session <
    unit, ids ascending (plan T9.2c; documents and sessions first because the screens lock them
    before the rows under them)."""

    documents: set[uuid.UUID] = field(default_factory=set[uuid.UUID])
    questions: set[uuid.UUID] = field(default_factory=set[uuid.UUID])
    filters: set[uuid.UUID] = field(default_factory=set[uuid.UUID])  # subject ids
    study_sessions: set[uuid.UUID] = field(default_factory=set[uuid.UUID])
    units: set[uuid.UUID] = field(default_factory=set[uuid.UUID])

    def acquire(self, session: Session, user_id: uuid.UUID) -> None:
        documents = DocumentRepository(session, user_id)
        for document_id in sorted(self.documents):
            documents.lock(document_id)
        if self.documents:
            DocSectionRepository(session, user_id).lock_of_documents(sorted(self.documents))
        if self.questions:
            QuestionRepository(session, user_id).lock_ids(sorted(self.questions))
        filters = StudyFilterRepository(session, user_id)
        for subject_id in sorted(self.filters):
            filters.lock(subject_id)
        drafts = DraftRepository(session, user_id)
        drafts.lock_sessions(sorted(self.study_sessions))
        if self.units:
            drafts.lock(sorted(self.units))


_ID_FIELDS = {
    "card": "card",
    "cards": "card",
    "section": "section",
    "sections": "section",
    "question": "question",
    "subject": "subject",
    "question_type": "question_type",
    "document": "document",
}


def _wanted(ops: Sequence[Op]) -> dict[str, set[uuid.UUID]]:
    """Every id the ops name, by the kind of record it must be."""
    found: dict[str, set[uuid.UUID]] = {}
    for op in ops:
        for name, kind in _ID_FIELDS.items():
            value = getattr(op, name, None)
            if value is None:
                continue
            ids: list[uuid.UUID] = list(value) if isinstance(value, list | tuple) else [value]  # pyright: ignore[reportUnknownArgumentType]
            found.setdefault(kind, set()).update(ids)
        if isinstance(op, SuggestOnlySubject | SuggestDeferSubject):
            found.setdefault("filter", set()).add(op.subject)
    return found


_CODES: dict[type[Exception], str] = {
    SectionNotFoundError: "not_owned",
    QuestionNotFoundError: "not_owned",
    NoChangeError: "no_change",
    RangeError: "invalid_range",
}


def _title_of(content: str) -> str:
    first = next((line.strip() for line in content.splitlines() if line.strip()), "")
    return first[:200] or "Thẻ mới"


def _s(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


@dataclass
class _Ctx:
    """What a run knows: the rows read after the locks, the writes' before-images and the ids of
    the cards a command made (domain id to database id)."""

    command_id: uuid.UUID
    now: datetime
    units: dict[uuid.UUID, KnowledgeUnit] = field(default_factory=dict[uuid.UUID, KnowledgeUnit])
    sections: dict[uuid.UUID, DocSection] = field(default_factory=dict[uuid.UUID, DocSection])
    by_document: dict[uuid.UUID, list[DocSection]] = field(
        default_factory=dict[uuid.UUID, list[DocSection]]
    )
    questions: dict[uuid.UUID, Question] = field(default_factory=dict[uuid.UUID, Question])
    subjects: set[uuid.UUID] = field(default_factory=set[uuid.UUID])
    # (table, id) -> revert, first touch wins; `owner` says which change of the diff it belongs to
    reverts: dict[tuple[str, uuid.UUID], dict[str, Any]] = field(
        default_factory=dict[tuple[str, uuid.UUID], dict[str, Any]]
    )
    owner: dict[tuple[str, uuid.UUID], tuple[str, uuid.UUID]] = field(
        default_factory=dict[tuple[str, uuid.UUID], tuple[str, uuid.UUID]]
    )
    made: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict[uuid.UUID, uuid.UUID])

    def keep(
        self,
        table: str,
        id_: uuid.UUID,
        before: dict[str, Any] | None,
        owner: tuple[str, uuid.UUID],
    ) -> None:
        key = (table, id_)
        if key not in self.reverts:
            self.reverts[key] = {"table": table, "id": str(id_), "before": before}
            self.owner[key] = owner


def _row(section: DocSection) -> rules.SectionRow:
    return rules.SectionRow(
        section.id,
        section.parent_id,
        section.first_page or 0,
        section.last_page or 0,
        section.weight,
        section.studied_weight,
        section.excluded,
    )


class CommandService:
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.log = CommandLogRepository(session, user_id)

    # --- apply ---------------------------------------------------------------------------

    def apply(
        self,
        command_id: uuid.UUID,
        session_id: uuid.UUID,
        request: CommandRequest,
        *,
        parse: Parser,
        now: datetime | None = None,
    ) -> ApplyOutcome:
        """Run the command once. Raises `CommandIdReused` (409) or `CommandRejected` (a code the
        route turns into 422, or 404 for `not_owned`)."""
        digest = payload_hash(request.raw_text, session_id, request.ops)
        stored = self.log.by_command_id(command_id)
        if stored is not None:
            return self._replay(stored, digest)
        if request.ops is None:
            self.session.commit()  # no read transaction stays open across the parser's call
            raw_ops = parse(request.raw_text)
        else:
            raw_ops = request.ops
        ops = validate_ops(raw_ops)
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"command:{self.user_id}:{command_id}"},
        )
        stored = self.log.by_command_id(command_id)
        if stored is not None:  # a twin finished while this one waited
            return self._replay(stored, digest)
        try:
            with self.session.begin_nested():
                outcome = self._run(
                    command_id, session_id, request, digest, ops, now or datetime.now(UTC)
                )
        except _Raced:
            stored = self.log.by_command_id(command_id)
            assert stored is not None
            return self._replay(stored, digest)
        except IntegrityError:
            raise CommandRejected("conflict") from None  # the error text carries row values
        logger.info(
            "command applied id=%s ops=%d affected=%d kinds=%s",
            command_id,
            len(ops),
            outcome.affected,
            ",".join(outcome.op_kinds),
        )
        return outcome

    def _replay(self, stored: CommandLog, digest: str) -> ApplyOutcome:
        if stored.payload_hash != digest:
            raise CommandIdReused
        entries: list[Entry] = list(stored.inverse_json)
        return ApplyOutcome(
            stored.command_id,
            stored.status,
            [self._shown(e) for e in entries],
            stored.affected_count,
            [o["kind"] for o in stored.ops_json],
            replayed=True,
        )

    @staticmethod
    def _shown(entry: Entry) -> dict[str, Any]:
        return {k: entry[k] for k in ("kind", "id", "verb", "before", "after")}

    # --- one run, inside the command's savepoint -------------------------------------------

    def _run(
        self,
        command_id: uuid.UUID,
        session_id: uuid.UUID,
        request: CommandRequest,
        digest: str,
        ops: list[Op],
        now: datetime,
    ) -> ApplyOutcome:
        wanted = _wanted(ops)
        self._lock(ops, wanted)
        ctx = _Ctx(command_id, now)
        start = self._load(ctx, wanted)
        for kind, ids in wanted.items():  # an id that is not this user's looks like a missing one
            for id_ in sorted(ids):
                if kind != "filter" and start.get(kind, id_) is None:
                    raise CommandRejected("not_owned", f"{kind} {id_}")
        ops = [self._in_order(op, ctx) for op in ops]

        steps: list[tuple[Op, Snapshot, tuple[Change, ...]]] = []
        state = start
        for op in ops:  # the whole command in memory first: a rejected op writes nothing
            after = run_op(state, op, uuid.uuid4)
            steps.append((op, after, diff(state, after)))
            state = after
        for op, after, changes in steps:
            self._write(ctx, op, changes, after)
        self.session.flush()

        entries = self._entries(ctx, diff(start, state))
        undo_revs: dict[str, int] = {}
        for entry in entries:
            for revert in entry["reverts"]:
                rev = self._rev(revert["table"], uuid.UUID(revert["id"]))
                revert["expected_rev"] = rev
                undo_revs[f"{revert['table']}:{revert['id']}"] = rev
        row = self.log.add_new(
            command_id=command_id,
            payload_hash=digest,
            raw_text=request.raw_text if request.raw_text.strip() else "[ops]",
            ops=[op_to_json(op) for op in ops],
            inverse=entries,
            affected_count=len(entries),
            screen_session_id=session_id,
            subject_id=self._subject_of(ctx),
            undo_revs=undo_revs,
        )
        if row is None:
            raise _Raced
        return ApplyOutcome(
            command_id,
            "applied",
            [self._shown(e) for e in entries],
            len(entries),
            [kind_of(op) for op in ops],
        )

    # --- locks and loading ---------------------------------------------------------------

    def _lock(self, ops: Sequence[Op], wanted: dict[str, set[uuid.UUID]]) -> None:
        targets = LockTargets()
        sections = DocSectionRepository(self.session, self.user_id).by_ids(
            sorted(wanted.get("section", ()))
        )
        targets.documents = {s.document_id for s in sections}
        targets.questions = set(wanted.get("question", ()))
        targets.filters = set(wanted.get("filter", ()))
        targets.units = set(wanted.get("card", ()))
        units = KnowledgeUnitRepository(self.session, self.user_id).by_ids(sorted(targets.units))
        targets.study_sessions = {u.session_id for u in units if u.session_id is not None}
        drafts = DraftRepository(self.session, self.user_id)
        for op in ops:
            if isinstance(op, CardAdd) and op.section is not None:
                owned = next((s for s in sections if s.id == op.section), None)
                found = None if owned is None else drafts.draft_session_of(owned.subject_id)
                if found is not None:
                    targets.study_sessions.add(found.id)
        targets.acquire(self.session, self.user_id)

    def _load(self, ctx: _Ctx, wanted: dict[str, set[uuid.UUID]]) -> Snapshot:
        records: list[Record] = []
        uid = self.user_id
        for unit in KnowledgeUnitRepository(self.session, uid).by_ids(
            sorted(wanted.get("card", ()))
        ):
            ctx.units[unit.id] = unit
            status = {"draft": CardStatus.DRAFT, "canonical": CardStatus.CANONICAL}.get(
                unit.status, CardStatus.DISCARDED
            )
            records.append(Card(unit.id, uid, unit.version, unit.summary, status, unit.section_id))
        sections = DocSectionRepository(self.session, uid)
        for section in sections.by_ids(sorted(wanted.get("section", ()))):
            ctx.sections[section.id] = section
            if section.document_id not in ctx.by_document:
                ctx.by_document[section.document_id] = sections.of_document(section.document_id)
        for document_id, rows in ctx.by_document.items():
            sub = [_row(s) for s in rows]
            leaf_ids = {r.id for r in rules.leaves(sub)}
            by_id = {s.id: s for s in rows}
            for section_id in sorted(wanted.get("section", ())):
                s = by_id.get(section_id)
                if s is None or s.document_id != document_id:
                    continue
                tree = [by_id[i] for i in rules.subtree_ids(sub, s.id) if i in leaf_ids]
                studied = bool(tree) and all(0 < x.weight <= x.studied_weight for x in tree)
                records.append(
                    Section(
                        s.id,
                        uid,
                        s.version,
                        s.first_page or 1,
                        s.last_page or 1,
                        s.excluded,
                        studied,
                    )
                )
        removals = PracticeRemovalRepository(self.session, uid)
        for question in QuestionRepository(self.session, uid).by_ids(
            sorted(wanted.get("question", ()))
        ):
            ctx.questions[question.id] = question
            records.append(
                QuestionRecord(
                    question.id,
                    uid,
                    question.version,
                    question.type_id,
                    None,
                    None,
                    question.answer_text or "",
                    removals.in_practice(question.id),
                )
            )
        subjects = SubjectRepository(self.session, uid)
        filters = StudyFilterRepository(self.session, uid)
        for subject_id in sorted(wanted.get("subject", ())):
            if subjects.get(subject_id) is not None:
                ctx.subjects.add(subject_id)
                records.append(Subject(subject_id, uid))
                state = filters.state(subject_id)
                if state.mode is not None and state.until is not None:
                    records.append(StudyFilter(subject_id, uid, state.rev, state.mode, state.until))
        types = PracticeTypeRepository(self.session, uid)
        for type_id in sorted(wanted.get("question_type", ())):
            if types.get(type_id) is not None:
                records.append(QuestionTypeRecord(type_id, uid))
        documents = DocumentRepository(self.session, uid)
        for document_id in sorted(wanted.get("document", ())):
            if documents.get(document_id) is not None:
                records.append(Document(document_id, uid))
        return Snapshot.of(uid, records)

    @staticmethod
    def _in_order(op: Op, ctx: _Ctx) -> Op:
        """A merge keeps the oldest card and joins the texts oldest first, as the review screen
        does: the op's card list is put in that order before it runs."""
        if not isinstance(op, CardMerge):
            return op
        have = [ctx.units[c] for c in op.cards if c in ctx.units]
        if len(have) != len(op.cards):
            return op
        ordered = sorted(have, key=lambda u: (u.created_at, str(u.id)))
        return replace(op, cards=[u.id for u in ordered])

    # --- writes: one op at a time, through the same services as the screens ----------------------

    def _write(self, ctx: _Ctx, op: Op, changes: tuple[Change, ...], after: Snapshot) -> None:
        if not changes:
            return
        try:
            self._dispatch(ctx, op, changes, after)
        except (NotADraft, UnitNotFound, SessionNotFound, UnitChangedElsewhere) as error:
            raise CommandRejected(type(error).__name__.lower()) from None
        except (SectionNotFoundError, NoChangeError, RangeError, QuestionNotFoundError) as error:
            raise CommandRejected(_CODES[type(error)]) from None

    def _dispatch(self, ctx: _Ctx, op: Op, changes: tuple[Change, ...], after: Snapshot) -> None:
        review = UnitReviewService(self.session, self.user_id)
        if isinstance(op, CardEdit | CardAddIdea):
            card = after.get("card", op.card)
            assert isinstance(card, Card)
            self._edit_card(ctx, review, op.card, card.text)
        elif isinstance(op, CardDiscardDraft):
            unit = ctx.units[op.card]
            ctx.keep("unit", unit.id, self._unit_image(unit), ("card", unit.id))
            review.discard(unit.id, ctx.now)
        elif isinstance(op, CardMerge):
            self._merge(ctx, review, op)
        elif isinstance(op, CardSplit):
            self._split(ctx, review, op, changes, after)
        elif isinstance(op, CardAdd):
            self._add_card(ctx, review, op, changes)
        elif isinstance(op, SectionExclude | SectionMark):
            self._sections(ctx, op, changes)
        elif isinstance(op, SuggestOnlySubject | SuggestDeferSubject):
            self._filter(ctx, op)
        elif isinstance(op, QuestionSetType | QuestionSetAnswer):
            self._question(ctx, op)
        elif isinstance(op, QuestionRemoveFromPractice):
            ctx.keep(
                "practice_removal", op.question, {"in_practice": True}, ("question", op.question)
            )
            practice.remove(
                self.session, self.user_id, op.question, ctx.now, command_id=ctx.command_id
            )
        else:  # pragma: no cover - validate_ops lets nothing else through
            raise CommandRejected("unsupported", kind_of(op))

    @staticmethod
    def _unit_image(unit: KnowledgeUnit) -> dict[str, Any]:
        return {
            "summary": unit.summary,
            "status": unit.status,
            "retired_at": None if unit.retired_at is None else unit.retired_at.isoformat(),
        }

    def _edit_card(
        self, ctx: _Ctx, review: UnitReviewService, id_: uuid.UUID, content: str
    ) -> None:
        unit = ctx.units[id_]
        if unit.status != "draft":  # a canonical card is edited by a new revision: not by a command
            raise CommandRejected("canonical_card", str(id_))
        ctx.keep("unit", id_, self._unit_image(unit), ("card", id_))
        review.edit(id_, unit.version, content=content)

    def _merge(self, ctx: _Ctx, review: UnitReviewService, op: CardMerge) -> None:
        units = [ctx.units[c] for c in op.cards]
        sessions = {u.session_id for u in units}
        study_id = next(iter(sessions))
        if len(sessions) != 1 or study_id is None:
            raise CommandRejected("not_a_draft")
        repo = DraftRepository(self.session, self.user_id)
        anchors = repo.anchors_of([u.id for u in units])
        sections = repo.sections_of([u.id for u in units])
        for i, unit in enumerate(units):
            image = self._unit_image(unit)
            if i == 0:
                image["section_ids"] = [str(s) for s in sections.get(unit.id, [])]
            else:
                image["anchor_ids"] = [str(a.id) for a in anchors.get(unit.id, [])]
            ctx.keep("unit", unit.id, image, ("card", unit.id))
        review.merge(study_id, [u.id for u in units])

    def _split(
        self,
        ctx: _Ctx,
        review: UnitReviewService,
        op: CardSplit,
        changes: tuple[Change, ...],
        after: Snapshot,
    ) -> None:
        parent = ctx.units[op.card]
        parent_card = after.get("card", op.card)
        assert isinstance(parent_card, Card)
        self._edit_card(ctx, review, op.card, parent_card.text)
        repo = DraftRepository(self.session, self.user_id)
        sections = repo.sections_of([parent.id]).get(parent.id, [])
        lineage = UnitLineageRepository(self.session, self.user_id)
        for change in changes:
            if change.before is not None or change.after is None:
                continue
            new = after.get("card", change.id)
            assert isinstance(new, Card) and parent.session_id is not None
            new_id = repo.insert_draft(
                subject_id=parent.subject_id,
                session_id=parent.session_id,
                draft_key=None,
                title=parent.title,
                summary=new.text,
                kind=parent.kind,
                section_id=parent.section_id,
                run_id=parent.run_id,
            )
            assert new_id is not None
            repo.add_revision(
                new_id, 0, "user", revision_content(parent.title, new.text, parent.kind)
            )
            repo.add_sections(new_id, parent.subject_id, sections)
            lineage.create(parent.id, new_id, parent.run_id)
            ctx.made[change.id] = new_id
            ctx.keep("unit", new_id, None, ("card", change.id))

    def _add_card(
        self, ctx: _Ctx, review: UnitReviewService, op: CardAdd, changes: tuple[Change, ...]
    ) -> None:
        if op.section is None:
            raise CommandRejected("section_required")
        section = ctx.sections[op.section]
        study = DraftRepository(self.session, self.user_id).draft_session_of(section.subject_id)
        if study is None:
            raise CommandRejected("no_open_session")
        change = next(c for c in changes if c.before is None)
        assert isinstance(change.after, Card)
        unit = review.add(
            study.id,
            title=_title_of(change.after.text),
            content=change.after.text,
            kind="concept",
            section_id=op.section,
        )
        ctx.made[change.id] = unit.id
        ctx.keep("unit", unit.id, None, ("card", change.id))

    def _sections(
        self, ctx: _Ctx, op: SectionExclude | SectionMark, changes: tuple[Change, ...]
    ) -> None:
        outline = OutlineService(self.session, self.user_id)
        for change in changes:
            section = ctx.sections[change.id]
            owner = ("section", section.id)
            if isinstance(op, SectionExclude):
                image = {"excluded": section.excluded, "source": section.source}
                ctx.keep("doc_section", section.id, image, owner)
                outline.edit_section(section.id, excluded=True)
            else:
                rows = ctx.by_document[section.document_id]
                sub = [_row(s) for s in rows]
                leaf_ids = {r.id for r in rules.leaves(sub)}
                by_id = {s.id: s for s in rows}
                for sid in rules.subtree_ids(sub, section.id):
                    if sid in leaf_ids:
                        image = {"studied_weight": by_id[sid].studied_weight}
                        ctx.keep("doc_section", sid, image, owner)
                outline.edit_section(section.id, studied=op.studied)

    def _filter(self, ctx: _Ctx, op: SuggestOnlySubject | SuggestDeferSubject) -> None:
        filters = StudyFilterRepository(self.session, self.user_id)
        before = filters.state(op.subject)
        image = {
            "mode": before.mode,
            "until": None if before.until is None else before.until.isoformat(),
        }
        ctx.keep("study_filter", op.subject, image, ("filter", op.subject))
        mode = "only" if isinstance(op, SuggestOnlySubject) else "defer"
        filters.set(op.subject, mode, op.until)

    def _question(self, ctx: _Ctx, op: QuestionSetType | QuestionSetAnswer) -> None:
        question = ctx.questions[op.question]
        owner = ("question", question.id)
        if isinstance(op, QuestionSetType):
            ctx.keep("question", question.id, {"type_id": _s(question.type_id)}, owner)
            question.type_id = op.question_type
        else:
            image = {"answer_text": question.answer_text, "answer_origin": question.answer_origin}
            ctx.keep("question", question.id, image, owner)
            question.answer_text, question.answer_origin = op.text, "user"
        self.session.flush()

    # --- the log entry ---------------------------------------------------------------------

    @staticmethod
    def _entries(ctx: _Ctx, changes: tuple[Change, ...]) -> list[Entry]:
        entries: list[Entry] = []
        for change in changes:
            key = (change.kind, change.id)
            made = ctx.made.get(change.id)
            before, after = record_to_json(change.before), record_to_json(change.after)
            if made is not None and after is not None:
                after["id"] = str(made)
            entries.append(
                {
                    "kind": change.kind,
                    "id": str(made or change.id),
                    "verb": "added" if change.before is None else "changed",
                    "before": before,
                    "after": after,
                    "reverts": [ctx.reverts[k] for k, owner in ctx.owner.items() if owner == key],
                }
            )
        seen = {(e["kind"], e["id"]) for e in entries}
        extra: dict[tuple[str, uuid.UUID], list[dict[str, Any]]] = {}
        for key, owner in ctx.owner.items():
            if (owner[0], str(ctx.made.get(owner[1], owner[1]))) not in seen:
                extra.setdefault(owner, []).append(ctx.reverts[key])
        for (kind, id_), reverts in extra.items():  # written, then written back to the start
            entries.append(
                {
                    "kind": kind,
                    "id": str(id_),
                    "verb": "changed",
                    "before": None,
                    "after": None,
                    "reverts": reverts,
                }
            )
        return entries

    def _rev(self, table: str, id_: uuid.UUID) -> int:
        uid = self.user_id
        if table == "doc_section":
            return DocSectionRepository(self.session, uid).by_ids([id_])[0].version
        if table == "question":
            return QuestionRepository(self.session, uid).by_ids([id_])[0].version
        if table == "unit":
            return KnowledgeUnitRepository(self.session, uid).by_ids([id_])[0].version
        if table == "practice_removal":
            return PracticeRemovalRepository(self.session, uid).rev(id_)
        return StudyFilterRepository(self.session, uid).state(id_).rev

    @staticmethod
    def _subject_of(ctx: _Ctx) -> uuid.UUID | None:
        found: set[uuid.UUID] = {u.subject_id for u in ctx.units.values()}
        found |= {s.subject_id for s in ctx.sections.values()}
        found |= {q.subject_id for q in ctx.questions.values()}
        found |= ctx.subjects
        return next(iter(found)) if len(found) == 1 else None
