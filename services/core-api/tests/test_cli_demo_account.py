"""Hackathon C7: the demo account has cards due today and practice questions ready."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.cli_demo_account import DEMO_EMAIL, DEMO_PASSWORD, DEMO_SUBJECT, seed_account
from core_api.db.models import Anchor, DocSection, Document, KnowledgeUnit
from core_api.domain.auth.passwords import verify_password
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.today import TodayRepository
from core_api.repositories.user import UserRepository


def test_demo_account_has_due_cards_and_ready_practice(db_session: Session) -> None:
    seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)
    user = UserRepository(db_session).get_by_email(DEMO_EMAIL)
    assert user is not None
    assert user.email_verified_at is not None
    assert user.password_hash is not None and verify_password(user.password_hash, DEMO_PASSWORD)
    today = TodayRepository(db_session, user.id)
    assert len(today.scheduled_units()) == 4
    assert len(today.practice_candidates()) == 3  # the fourth waits for an unstudied section


def test_demo_account_runs_twice_without_adding(db_session: Session) -> None:
    seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)
    assert "already there" in seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)


def test_demo_account_runs_again_with_the_textbook_in_any_status(db_session: Session) -> None:
    seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)
    for doc in db_session.scalars(select(Document)):
        doc.status = "failed"
        doc.failure_reason = "unreadable"
        doc.run_id = doc.toc_key = doc.page_labels_key = doc.page_text_key = None
        doc.thumbnails_prefix = None
    db_session.flush()
    assert "already there" in seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)
    user = UserRepository(db_session).get_by_email(DEMO_EMAIL)
    assert user is not None
    names = [s.name for s, _, _ in SubjectRepository(db_session, user.id).list_with_exams()]
    assert names.count(DEMO_SUBJECT) == 1


def test_demo_textbook_is_indexed_with_chapters_and_cards_sit_in_a_session(
    db_session: Session,
) -> None:
    """The outline must not wait on "Đang đọc mục lục" and Kho kiến thức must not be empty."""
    seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)
    user = UserRepository(db_session).get_by_email(DEMO_EMAIL)
    assert user is not None
    document = db_session.scalars(select(Document).where(Document.user_id == user.id)).one()
    assert document.status == "indexed"
    sections = list(db_session.scalars(select(DocSection).where(DocSection.user_id == user.id)))
    assert len([s for s in sections if s.parent_id is None]) == 2
    units = list(db_session.scalars(select(KnowledgeUnit).where(KnowledgeUnit.user_id == user.id)))
    assert units and all(u.session_id is not None for u in units)


def test_every_demo_unit_has_a_source_anchor_so_grading_is_not_refused(
    db_session: Session,
) -> None:
    """Hackathon V2: no anchor meant `RequestRefused("anchor count")` and "Chưa chấm được"."""
    seed_account(db_session, DEMO_EMAIL, DEMO_PASSWORD)
    user = UserRepository(db_session).get_by_email(DEMO_EMAIL)
    assert user is not None
    units = list(db_session.scalars(select(KnowledgeUnit).where(KnowledgeUnit.user_id == user.id)))
    anchored = {
        a.unit_id for a in db_session.scalars(select(Anchor).where(Anchor.user_id == user.id))
    }
    assert units and {u.id for u in units} <= anchored
