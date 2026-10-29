# pyright: reportPrivateUsage=false
"""T5.5a (US-10): what `ProgressRepository` computes from the database, for one user. The pure
rules are in tests/domain/test_progress.py. Isolation of two users is tested at the end."""

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from core_api.db.models import (
    Document,
    ReviewSession,
    SessionRange,
    StudySession,
    Subject,
    User,
)
from core_api.domain.scheduling.fsrs_adapter import MemoryState, Phase
from core_api.repositories.progress import ProgressRepository
from core_api.repositories.review import MemoryStateRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository

NOW = datetime(2026, 10, 23, 1, 0, tzinfo=UTC)
TODAY = date(2026, 10, 23)
RUN = uuid.uuid4()


class World:
    """One user's subjects, units, schedules, documents and sessions, written directly."""

    def __init__(self, session: Session, user: User) -> None:
        self.session, self.user = session, user

    def subject(self, name: str = "Mạng", exam_in: int | None = 30) -> Subject:
        repo = SubjectRepository(self.session, self.user.id)
        if exam_in is None:
            subject = repo.create(name)
        else:
            subject, _ = repo.create_with_exam(name, TODAY + timedelta(days=exam_in))
        self.session.flush()
        return subject

    def unit(
        self, subject: Subject, *, stability: float | None = None, skipped: bool = False
    ) -> uuid.UUID:
        """A unit; `stability` None leaves it never asked. Last review is 1 day ago, so a
        stability of 1000 recalls ~100% and 0.1 recalls far below 90%."""
        unit = KnowledgeUnitRepository(self.session, self.user.id).create(
            subject.id, title=f"u{uuid.uuid4().hex[:6]}", summary="s", kind="concept", run_id=RUN
        )
        if skipped:
            unit.skipped_at = NOW
        if stability is not None:
            MemoryStateRepository(self.session, self.user.id).upsert(
                unit.id,
                "core",
                MemoryState(
                    phase=Phase.REVIEW,
                    step=None,
                    stability=stability,
                    difficulty=5.0,
                    due=NOW + timedelta(days=1),
                    last_review=NOW - timedelta(days=1),
                ),
            )
        self.session.flush()
        return unit.id

    def document(self, subject: Subject, pages: int, name: str = "Giáo trình") -> Document:
        sha = uuid.uuid4().hex * 2
        run = uuid.uuid4()
        prefix = f"users/{self.user.id}/subjects/{subject.id}/derived/{run}"
        document = Document(
            subject_id=subject.id,
            short_name=name,
            sha256=sha,
            size_bytes=100,
            object_key=f"users/{self.user.id}/subjects/{subject.id}/raw/{sha}.pdf",
            status="indexed",
            presigned_at=NOW,
            uploaded_at=NOW,
            run_id=run,
            page_count=pages,
            unreadable_pages=[],
            toc_key=f"{prefix}/toc.json",
            page_labels_key=f"{prefix}/page_labels.json",
            page_text_key=f"{prefix}/page_text.json",
            thumbnails_prefix=f"{prefix}/thumbs",
        )
        document.user_id = self.user.id
        self.session.add(document)
        self.session.flush()
        return document

    def failed_document(self, subject: Subject) -> None:
        """A file that could not be read: no page count, never part of the total."""
        sha = uuid.uuid4().hex * 2
        document = Document(
            subject_id=subject.id,
            short_name="Hỏng",
            sha256=sha,
            size_bytes=100,
            object_key=f"users/{self.user.id}/subjects/{subject.id}/raw/{sha}.pdf",
            status="failed",
            presigned_at=NOW,
            uploaded_at=NOW,
            failure_reason="unreadable",
            unreadable_pages=[],
        )
        document.user_id = self.user.id
        self.session.add(document)
        self.session.flush()

    def studied(
        self,
        subject: Subject,
        document: Document,
        first: int,
        last: int,
        *,
        status: str = "confirmed",
        position: int = 0,
    ) -> StudySession:
        confirmed = status == "confirmed"
        study = StudySession(
            subject_id=subject.id,
            description_raw="RIÊNG TƯ: mô tả của người học",
            extraction="proposed",
            status=status,
            studied_on=TODAY if confirmed else None,
            learning_day=TODAY if confirmed else None,
            confirmed_at=NOW if confirmed else None,
        )
        study.user_id = self.user.id
        self.session.add(study)
        self.session.flush()
        rng = SessionRange(
            session_id=study.id,
            document_id=document.id,
            start_page=first,
            end_page=last,
            depth="deep",
            position=position,
        )
        rng.user_id = self.user.id
        self.session.add(rng)
        self.session.flush()
        return study

    def sitting(self, day: date, minutes: int | None) -> None:
        start = datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        sitting = ReviewSession(
            learning_day=day,
            started_at=start,
            ended_at=None if minutes is None else start + timedelta(minutes=minutes),
            stop_reason=None if minutes is None else "completed",
        )
        sitting.user_id = self.user.id
        self.session.add(sitting)
        self.session.flush()


def progress(session: Session, user: User) -> ProgressRepository:
    return ProgressRepository(session, user.id)


def only(session: Session, user: User):  # noqa: ANN201
    (subject,) = progress(session, user).subjects(NOW, TODAY)
    return subject


# US-10 AC2. Red when: overlapping sessions count a page twice, or an unconfirmed draft counts.
def test_us10_ac2_coverage_is_the_union_of_confirmed_ranges(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    world = World(db_session, two_users[0])
    subject = world.subject()
    doc = world.document(subject, 100)
    world.studied(subject, doc, 1, 10)
    world.studied(subject, doc, 6, 15)
    world.studied(subject, doc, 50, 60, status="draft")
    result = only(db_session, two_users[0])
    assert (result.pages_covered, result.pages_total) == (15, 100)


# US-10 AC1. Red when: the total leaves out a document, or counts one not indexed.
def test_us10_ac1_total_pages_of_all_indexed_documents(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    world = World(db_session, two_users[0])
    subject = world.subject()
    first, second = world.document(subject, 40), world.document(subject, 60)
    world.studied(subject, first, 1, 40)
    world.studied(subject, second, 1, 10)
    world.failed_document(subject)
    result = only(db_session, two_users[0])
    assert (result.pages_covered, result.pages_total) == (50, 100)


# US-10 AC5. Red when: skipped units reach "vững" or the ready share, or are not reported.
def test_us10_ac5_skipped_units_are_left_out_and_counted(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    world = World(db_session, two_users[0])
    subject = world.subject()
    world.unit(subject, stability=1000)
    world.unit(subject, stability=1000)
    world.unit(subject, skipped=True)  # never asked, skipped: must not block "ready"
    world.unit(subject, stability=0.1, skipped=True)
    r = only(db_session, two_users[0]).readiness
    assert (r.units, r.asked, r.solid, r.skipped, r.ready) == (2, 2, 2, 2, True)


# Q1 tạm. Red when: a never-asked unit does not block ready, or the threshold is 100%.
def test_q1_ready_needs_all_asked_and_85_percent_solid(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    world = World(db_session, two_users[0])
    subject = world.subject()
    for _ in range(17):
        world.unit(subject, stability=1000)
    for _ in range(3):
        world.unit(subject, stability=0.1)  # asked, recall far below 90%
    r = only(db_session, two_users[0]).readiness
    assert (r.units, r.asked, r.solid, r.ready) == (20, 20, 17, True)
    world.unit(subject)  # one never asked
    assert not only(db_session, two_users[0]).readiness.ready


# Q1 tạm: units of a soft-deleted or unrelated subject do not leak in; no exam is fine.
def test_subject_without_exam_and_deleted_subject(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    world = World(db_session, two_users[0])
    kept = world.subject("Giữ", exam_in=None)
    gone = world.subject("Xóa")
    world.unit(gone, stability=1000)
    gone.deleted_at = NOW
    db_session.flush()
    (result,) = progress(db_session, two_users[0]).subjects(NOW, TODAY)
    assert result.subject_id == kept.id and result.days_to_exam is None


def test_days_to_exam_counts_from_today(db_session: Session, two_users: tuple[User, User]) -> None:
    World(db_session, two_users[0]).subject(exam_in=30)
    assert only(db_session, two_users[0]).days_to_exam == 30


# US-10 AC4. Red when: hours do not match ended_at - started_at in the database.
def test_us10_ac4_weekly_hours_match_the_raw_sittings(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    world = World(db_session, two_users[0])
    world.sitting(date(2026, 10, 19), 90)
    world.sitting(date(2026, 10, 21), 30)
    world.sitting(date(2026, 10, 27), None)  # open
    weeks = progress(db_session, two_users[0]).weeks()
    assert [(w.week_start, w.hours) for w in weeks] == [
        (date(2026, 10, 19), 2.0),
        (date(2026, 10, 26), 0.0),
    ]


def parse(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


# US-10 AC3 + AC4. Red when: the CSV lacks ready days, weeks studied, hours, or the session log.
def test_us10_ac3_csv_has_subject_numbers_weeks_hours_and_log(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    world = World(db_session, two_users[0])
    subject = world.subject("Mạng")
    doc = world.document(subject, 50)
    world.studied(subject, doc, 1, 10)
    world.unit(subject, stability=1000)
    world.sitting(date(2026, 10, 19), 90)
    rows = parse(progress(db_session, two_users[0]).export_csv(NOW, TODAY))
    facts = {(r["section"], r["key"]): r for r in rows}
    assert facts["subject", "ready"]["value"] == "yes"
    assert facts["subject", "ready_days_before_exam"]["value"] == "30"
    assert facts["subject", "pages_covered"]["value"] == "10"
    assert facts["subject", "ready_note"]["value"] == "Q1 tạm"
    assert facts["summary", "weeks_studied"]["value"] == "1"
    assert facts["week", "hours"]["value"] == "1.50"
    assert facts["week", "hours"]["period"] == "2026-10-19"
    assert facts["review_session", "minutes"]["value"] == "90.0"
    assert facts["study_session", "pages"]["value"] == "10"
    assert facts["study_session", "pages"]["subject"] == "Mạng"


# US-10 Bảo mật. Red when: the learner's description or answers reach the CSV.
def test_csv_never_holds_the_learners_own_words(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    world = World(db_session, two_users[0])
    subject = world.subject()
    world.studied(subject, world.document(subject, 10), 1, 2)
    text = progress(db_session, two_users[0]).export_csv(NOW, TODAY)
    assert "RIÊNG TƯ" not in text


# US-10 AC3 + ADR-0001. Red when: a query of the repository forgets the user filter.
def test_us10_ac3_two_users_never_see_each_others_progress(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    mine = World(db_session, alice)
    subject = mine.subject("Môn riêng của Alice")
    doc = mine.document(subject, 80)
    mine.studied(subject, doc, 1, 20)
    mine.unit(subject, stability=1000)
    mine.sitting(date(2026, 10, 19), 60)

    theirs = ProgressRepository(db_session, bob.id)
    assert theirs.subjects(NOW, TODAY) == []
    assert theirs.weeks() == []
    # each read on its own: the user filter must hold in every query, not only through subjects
    assert theirs._pages() == {}
    assert theirs._units(NOW) == ({}, {})
    assert theirs._confirmed_sessions() == []
    assert theirs._review_sittings() == []
    other = parse(theirs.export_csv(NOW, TODAY))
    assert [r["section"] for r in other] == ["summary"]  # only weeks_studied = 0
    assert other[0]["value"] == "0"
    assert "Alice" not in theirs.export_csv(NOW, TODAY)

    # and Bob's own data does not change Alice's numbers
    his = World(db_session, bob)
    his_subject = his.subject("Môn của Bob")
    his.unit(his_subject)
    (result,) = ProgressRepository(db_session, alice.id).subjects(NOW, TODAY)
    assert (result.name, result.pages_covered, result.readiness.units) == (
        "Môn riêng của Alice",
        20,
        1,
    )
