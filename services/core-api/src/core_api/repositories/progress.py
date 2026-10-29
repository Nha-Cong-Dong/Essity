"""What the progress screen and the CSV export read (T5.5a, US-10): every query scoped to the
user, visible subjects only (not soft-deleted). Numbers are computed at read time (ADR-0008 §7);
the rules are in `domain.progress`. The endpoints (T5.5b) call `subjects`, `weeks`, `export_csv`."""

import uuid
from datetime import date, datetime

from sqlalchemy import and_, select

from core_api.db.models import (
    Document,
    Exam,
    KnowledgeUnit,
    MemoryState,
    ReviewSession,
    SessionRange,
    StudySession,
    Subject,
)
from core_api.domain.progress import (
    CsvRow,
    StudyWeek,
    SubjectProgress,
    UnitProgress,
    covered_pages,
    csv_text,
    readiness,
    study_weeks,
)
from core_api.domain.scheduling.fsrs_adapter import FsrsScheduler, Phase
from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
from core_api.repositories.base import UserScopedRepository

_SCHEDULER = FsrsScheduler()
Q1_NOTE = "Q1 tạm"  # the readiness definition is temporary (PRD §8.1)


class ProgressRepository(UserScopedRepository[MemoryState]):
    model = MemoryState

    def _visible_subjects(self) -> list[tuple[uuid.UUID, str, date | None]]:
        rows = self.session.execute(
            select(Subject.id, Subject.name, Exam.exam_date)
            .join(
                Exam,
                and_(Exam.subject_id == Subject.id, Exam.user_id == self.user_id),
                isouter=True,
            )
            .where(Subject.user_id == self.user_id, Subject.deleted_at.is_(None))
            .order_by(Subject.name, Subject.id)
        ).all()
        return [(sid, name, exam_date) for sid, name, exam_date in rows]

    def _pages(self) -> dict[uuid.UUID, tuple[int, int]]:
        """(covered, total) pages by subject: confirmed sessions over indexed documents."""
        documents = self.session.execute(
            select(Document.id, Document.subject_id, Document.page_count).where(
                Document.user_id == self.user_id,
                Document.status == "indexed",
                Document.page_count.is_not(None),
            )
        ).all()
        ranges = self.session.execute(
            select(
                StudySession.subject_id,
                SessionRange.document_id,
                SessionRange.start_page,
                SessionRange.end_page,
            )
            .join(
                StudySession,
                and_(
                    StudySession.id == SessionRange.session_id,
                    StudySession.user_id == self.user_id,
                ),
            )
            .where(SessionRange.user_id == self.user_id, StudySession.status == "confirmed")
        ).all()
        counts: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
        for document_id, subject_id, page_count in documents:
            counts.setdefault(subject_id, {})[document_id] = page_count
        spans: dict[uuid.UUID, list[tuple[uuid.UUID, int, int]]] = {}
        for subject_id, document_id, first, last in ranges:
            spans.setdefault(subject_id, []).append((document_id, first, last))
        return {
            subject_id: (covered_pages(spans.get(subject_id, []), mine), sum(mine.values()))
            for subject_id, mine in counts.items()
        }

    def _units(
        self, now: datetime
    ) -> tuple[dict[uuid.UUID, list[UnitProgress]], dict[uuid.UUID, int]]:
        """Active units that are not skipped, by subject, with their recall now; and the number
        skipped by subject. A unit is "asked" once it has a core schedule."""
        rows = self.session.execute(
            select(KnowledgeUnit.subject_id, KnowledgeUnit.skipped_at, MemoryState)
            .join(
                MemoryState,
                and_(
                    MemoryState.unit_id == KnowledgeUnit.id,
                    MemoryState.user_id == self.user_id,
                    MemoryState.facet == "core",
                ),
                isouter=True,
            )
            .where(KnowledgeUnit.user_id == self.user_id, KnowledgeUnit.status == "active")
        ).all()
        units: dict[uuid.UUID, list[UnitProgress]] = {}
        skipped: dict[uuid.UUID, int] = {}
        for subject_id, skipped_at, memory in rows:
            if skipped_at is not None:
                skipped[subject_id] = skipped.get(subject_id, 0) + 1
            elif memory is None:
                units.setdefault(subject_id, []).append(UnitProgress(False, None))
            else:
                state = State(
                    phase=Phase(memory.phase),
                    step=memory.step,
                    stability=memory.stability,
                    difficulty=memory.difficulty,
                    due=memory.due,
                    last_review=memory.last_review,
                )
                recall = _SCHEDULER.retrievability(state, now)
                units.setdefault(subject_id, []).append(UnitProgress(True, recall))
        return units, skipped

    def subjects(self, now: datetime, today: date) -> list[SubjectProgress]:
        """One entry per visible subject: pages, solid and ready counts (Q1 tạm), days to the
        exam. `today` is the user's learning day."""
        pages = self._pages()
        units, skipped = self._units(now)
        return [
            SubjectProgress(
                subject_id=sid,
                name=name,
                exam_date=exam_date,
                pages_covered=pages.get(sid, (0, 0))[0],
                pages_total=pages.get(sid, (0, 0))[1],
                readiness=readiness(units.get(sid, []), skipped.get(sid, 0)),
                days_to_exam=None if exam_date is None else (exam_date - today).days,
            )
            for sid, name, exam_date in self._visible_subjects()
        ]

    def _review_sittings(self) -> list[tuple[date, datetime, datetime | None]]:
        rows = self.session.execute(
            select(ReviewSession.learning_day, ReviewSession.started_at, ReviewSession.ended_at)
            .where(ReviewSession.user_id == self.user_id)
            .order_by(ReviewSession.learning_day, ReviewSession.started_at)
        ).all()
        return [(day, started, ended) for day, started, ended in rows]

    def weeks(self) -> list[StudyWeek]:
        """Weeks with a review sitting and their hours (US-10 AC4): for the CSV only."""
        return study_weeks(self._review_sittings())

    def _confirmed_sessions(self) -> list[tuple[uuid.UUID, date, int]]:
        """(subject, studied_on, pages) of confirmed sessions of visible subjects."""
        visible = select(Subject.id).where(
            Subject.user_id == self.user_id, Subject.deleted_at.is_(None)
        )
        sessions = self.session.execute(
            select(StudySession.id, StudySession.subject_id, StudySession.studied_on)
            .where(
                StudySession.user_id == self.user_id,
                StudySession.status == "confirmed",
                StudySession.subject_id.in_(visible),
            )
            .order_by(StudySession.studied_on, StudySession.confirmed_at)
        ).all()
        pages: dict[uuid.UUID, int] = {}
        for session_id, first, last in self.session.execute(
            select(SessionRange.session_id, SessionRange.start_page, SessionRange.end_page).where(
                SessionRange.user_id == self.user_id
            )
        ):
            pages[session_id] = pages.get(session_id, 0) + (last - first + 1)
        return [
            (subject_id, studied_on, pages.get(id, 0))
            for id, subject_id, studied_on in sessions
            if studied_on is not None
        ]

    def export_csv(self, now: datetime, today: date) -> str:
        """The user's whole log as CSV (US-10 AC3, AC4): numbers per subject, weeks studied and
        hours per week, review sittings, confirmed study sessions. Never the learner's own words
        (descriptions, answers): numbers, dates, subject names only."""
        rows: list[CsvRow] = []
        for subject in self.subjects(now, today):
            r, days = subject.readiness, subject.days_to_exam
            exam = "" if subject.exam_date is None else subject.exam_date.isoformat()
            facts: dict[str, object] = {
                "units": r.units,
                "units_asked": r.asked,
                "units_solid": r.solid,
                "units_skipped": r.skipped,
                "pages_covered": subject.pages_covered,
                "pages_total": subject.pages_total,
                "ready": "yes" if r.ready else "no",
                "ready_note": Q1_NOTE,
                "days_to_exam": "" if days is None else days,
                # Q1 tạm: the days left before the exam if the subject is ready as of today
                "ready_days_before_exam": days if r.ready and days is not None else "",
            }
            rows += [CsvRow("subject", subject.name, exam, k, str(v)) for k, v in facts.items()]
        weeks = self.weeks()
        rows.append(CsvRow("summary", "", "", "weeks_studied", str(len(weeks))))
        rows += [
            CsvRow("week", "", w.week_start.isoformat(), "hours", f"{w.hours:.2f}") for w in weeks
        ]
        for day, started, ended in self._review_sittings():
            minutes = "" if ended is None else f"{(ended - started).total_seconds() / 60:.1f}"
            rows.append(CsvRow("review_session", "", day.isoformat(), "minutes", minutes))
        names = {sid: name for sid, name, _ in self._visible_subjects()}
        rows += [
            CsvRow("study_session", names[sid], studied_on.isoformat(), "pages", str(pages))
            for sid, studied_on, pages in self._confirmed_sessions()
        ]
        return csv_text(rows)
