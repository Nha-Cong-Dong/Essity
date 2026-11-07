"""REVIEW-SEED: the review account has cards due, edges, a studied outline, practice due and
answered, and a question answered twice whose schedule follows the last attempt."""

import json
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.cli_review_account import (
    CARDS,
    EDGES,
    PRACTICE,
    REVIEW_SUBJECT,
    REVIEW_USERNAME,
    parse_args,
    seed_account,
)
from core_api.db.models import Grade, Question, UnitEdge, User
from core_api.domain.auth.passwords import verify_password
from core_api.domain.learning_day import learning_day
from core_api.domain.mastery import PracticeRating
from core_api.repositories.practice import PracticeLogRepository, PracticeStateRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.today import TodayRepository
from core_api.repositories.user import UserRepository
from core_api.services.outline import OutlineService
from core_api.services.practice_grading import override_practice_grade

NOW = datetime(2026, 11, 5, 3, 0, tzinfo=UTC)  # 10:00 in Ho Chi Minh City


def _outline() -> bytes:
    """The numbered titles of the real book, over 30 pages (the real file is built from the PDF
    by scripts/review_seed_outline.py and is not committed)."""
    nodes: list[dict[str, object]] = []

    def add(title: str, parent: int | None, first: int, last: int) -> int:
        nodes.append(
            {
                "title": title,
                "parent": parent,
                "page_start": first,
                "page_end": last,
                "weight": last - first + 1,
                "source": "heading",
            }
        )
        return len(nodes) - 1

    chapter = add("Chương 1. Biến cố ngẫu nhiên và xác suất", None, 1, 24)
    page = 1
    for number, parts in (("1.1.", 7), ("1.2.", 3), ("1.3.", 2), ("1.4.", 4)):
        first = page
        page += parts
        group = add(f"{number} Mục", chapter, first, page - 1)
        for i in range(parts):
            add(f"{number}{i + 1}. Tiểu mục", group, first + i, first + i)
    exercises = add("Bài tập chương 1", chapter, page, page + 2)
    assert exercises
    add("Chương 2. Biến ngẫu nhiên", None, page + 3, page + 6)
    return json.dumps({"unit": "page", "nodes": nodes}).encode()


def _seed(session: Session) -> tuple[str, str, str | None]:
    """Seed under an email and a name of this test's own: a real account may sit in the database."""
    tag = uuid.uuid4().hex[:10]
    email = f"review-{tag}@essity.test"
    line, password = seed_account(session, _outline(), NOW, email=email, username=f"r{tag}")
    return email, line, password


def _seeded(session: Session) -> User:
    email, _, _ = _seed(session)
    user = UserRepository(session).get_by_email(email)
    assert user is not None
    return user


def test_fresh_account_has_one_subject_and_a_verified_login(db_session: Session) -> None:
    email, line, password = _seed(db_session)
    assert password is not None and password not in line
    user = UserRepository(db_session).get_by_email(email)
    assert user is not None and user.email_verified_at is not None
    assert user.password_hash is not None and verify_password(user.password_hash, password)
    names = [s.name for s, _, _ in SubjectRepository(db_session, user.id).list_with_exams()]
    assert names == [REVIEW_SUBJECT]


def test_runs_twice_without_adding(db_session: Session) -> None:
    email, _, _ = _seed(db_session)
    user = UserRepository(db_session).get_by_email(email)
    assert user is not None
    tag = email.split("-")[1].split("@")[0]
    line, password = seed_account(db_session, _outline(), NOW, email=email, username=f"r{tag}")
    assert "already there" in line and password is None
    count = db_session.scalar(
        select(func.count()).select_from(Question).where(Question.user_id == user.id)
    )
    assert count == len(CARDS) + len(PRACTICE)


def test_cards_are_due_today_and_edges_link_them(db_session: Session) -> None:
    user = _seeded(db_session)
    scheduled = TodayRepository(db_session, user.id).scheduled_units()
    assert len(scheduled) == len(CARDS)
    due = [d for d in scheduled if d.state.due <= NOW]
    assert len(due) == sum(1 for c in CARDS if c.due_in_hours <= 0) > 5
    edges = list(db_session.scalars(select(UnitEdge).where(UnitEdge.user_id == user.id)))
    assert len(edges) == len(EDGES) and all(e.status == "active" for e in edges)


def test_outline_is_studied_in_part(db_session: Session) -> None:
    user = _seeded(db_session)
    subject = SubjectRepository(db_session, user.id).list_with_exams()[0][0]
    view = OutlineService(db_session, user.id).view(subject.id)
    assert 0.1 < view.progress < 0.9  # chapter 1 in part, chapter 2 untouched


def test_practice_is_due_today_and_answered(db_session: Session) -> None:
    user = _seeded(db_session)
    states = PracticeStateRepository(db_session, user.id)
    day = learning_day(NOW, ZoneInfo(user.timezone), user.day_start_hour)
    answered = {s.question_id for s in states.due_on(day)}
    assert len(answered) >= 3  # answered and due
    ready = TodayRepository(db_session, user.id).practice_candidates()
    assert ready  # never answered, ready to do


def _redone(db_session: Session, user: User) -> Question:
    prompts = {p.prompt for p in PRACTICE if len(p.history) == 2}
    return db_session.scalars(
        select(Question).where(Question.user_id == user.id, Question.prompt.in_(prompts))
    ).one()


def test_redone_and_regraded_question_follows_the_last_attempt(db_session: Session) -> None:
    user = _seeded(db_session)
    question = _redone(db_session, user)
    log = PracticeLogRepository(db_session, user.id).effective([question.id])
    assert len(log) == 2  # one effective row per attempt: the older attempt, then the last
    assert log[0].rating == PracticeRating.AGAIN
    assert log[1].rating == PracticeRating.GOOD  # "partial" regraded to correct
    states = PracticeStateRepository(db_session, user.id)
    before = states.state(question.id)
    assert before is not None and before.memory.last_review == log[1].reviewed_at
    # Regrade the last attempt again, on the web's "Chấm sai": the schedule moves with it.
    newest = db_session.scalars(
        select(Grade)
        .where(Grade.user_id == user.id, Grade.attempt_id == log[1].attempt_id)
        .order_by(Grade.seq.desc())
    ).first()
    assert newest is not None
    override_practice_grade(db_session, user.id, newest.id, "incorrect")
    after = states.state(question.id)
    assert after is not None
    assert after.memory.due < before.memory.due
    assert after.memory.last_review == before.memory.last_review


def test_password_is_never_in_what_the_cli_prints(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, password = _seed(db_session)
    assert password is not None
    assert password not in capsys.readouterr().out


def test_cli_takes_a_username_for_a_second_account() -> None:
    args = parse_args(["--outline", "o.json", "--email", "b@essity.test", "--username", "second"])
    assert args.username == "second" and args.email == "b@essity.test"
    assert parse_args(["--outline", "o.json"]).username == REVIEW_USERNAME
