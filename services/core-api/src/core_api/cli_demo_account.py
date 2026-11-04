"""`python -m core_api.cli_demo_account [--email E] [--password P]`: a ready demo account.

Hackathon 04/11 (C7). Creates a verified user with one subject (exam in 30 days), a textbook with a
four-section outline (two studied, two not), canonical cards due today, and bank practice
questions: three ready, one waiting for an unstudied section. Local and test only. Run twice, it
adds nothing (the user and the subject are found by email and name).

Cards and questions are written straight to the tables, with no AI call.
"""

import argparse
import hashlib
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.config import DEV_ENVIRONMENTS, get_settings
from core_api.db.engine import get_engine
from core_api.db.models import (
    DocSection,
    Document,
    KnowledgeUnit,
    MemoryState,
    Question,
    QuestionSection,
    QuestionUnit,
    StudySession,
    UnitSection,
    User,
)
from core_api.domain.auth.passwords import hash_password
from core_api.domain.learning_day import learning_day
from core_api.domain.question_hash import content_hash
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.user import UserRepository

DEMO_EMAIL = "demo@essity.test"
DEMO_PASSWORD = "Demo-Essity-2026"
DEMO_SUBJECT = "Mạng máy tính (tài khoản mẫu)"

# Two chapters over four leaf sections (the outline "còn n" counts chapters):
# (chapter title, [(leaf title, first page, last page, studied)])
_CHAPTERS = (
    (
        "Chương 1. Mạng và tầng giao vận",
        [("Giới thiệu mạng máy tính", 1, 20, True), ("Tầng giao vận: TCP và UDP", 21, 60, True)],
    ),
    (
        "Chương 2. Tầng mạng và bảo mật",
        [("Tầng mạng: định tuyến IP", 61, 100, False), ("Bảo mật mạng", 101, 130, False)],
    ),
)
# (title, summary, review question, answer, section index)
_CARDS = (
    (
        "Bắt tay ba bước TCP",
        "TCP mở kết nối bằng SYN, SYN-ACK, ACK.",
        "TCP thiết lập kết nối như thế nào?",
        "Bằng bắt tay ba bước: client gửi SYN, server trả SYN-ACK, client gửi ACK.",
        1,
    ),
    (
        "Timeout và gửi lại",
        "Gói mất thì chờ hết timeout rồi gửi lại.",
        "Gói SYN-ACK bị mất thì chuyện gì xảy ra?",
        "Client hết timeout thì gửi lại SYN; server gửi lại SYN-ACK.",
        1,
    ),
    (
        "UDP không kết nối",
        "UDP gửi ngay, không bảo đảm gói tới nơi.",
        "Vì sao UDP nhanh hơn TCP?",
        "UDP không bắt tay và không gửi lại gói mất, nên ít trễ hơn.",
        1,
    ),
    (
        "Mạng và gói tin",
        "Dữ liệu đi qua mạng dưới dạng gói tin.",
        "Gói tin là gì?",
        "Một đơn vị dữ liệu nhỏ được chia ra để truyền qua mạng.",
        0,
    ),
)
# (prompt, answer, section index): bank questions
_PRACTICE = (
    (
        "So sánh TCP và UDP về độ tin cậy.",
        "TCP bảo đảm thứ tự và gửi lại gói mất; UDP không bảo đảm.",
        1,
    ),
    ("Mô tả bắt tay ba bước của TCP.", "Client gửi SYN, server trả SYN-ACK, client gửi ACK.", 1),
    (
        "Gói tin là gì và vì sao mạng chia dữ liệu thành gói?",
        "Đơn vị dữ liệu nhỏ; chia gói để dùng chung đường truyền và gửi lại phần mất.",
        0,
    ),
    ("Bảng định tuyến IP dùng để làm gì?", "Chọn cổng ra cho gói tin theo địa chỉ đích.", 2),
)


def seed_account(session: Session, email: str, password: str, now: datetime | None = None) -> str:
    """Make the demo account, once. Returns a line to print."""
    now = now or datetime.now(UTC)
    users = UserRepository(session)
    user = users.get_by_email(email)
    if user is None:
        user = users.create(email, password_hash=hash_password(password))
        user.email_verified_at = now
        session.flush()
    elif user.email_verified_at is None:
        user.email_verified_at = now
    subjects = SubjectRepository(session, user.id)
    for old, _, _ in subjects.list_with_exams():
        if old.name != DEMO_SUBJECT:
            continue
        indexed = session.scalar(
            select(Document.id).where(
                Document.subject_id == old.id,
                Document.user_id == user.id,
                Document.status == "indexed",
            )
        )
        if indexed is not None:
            return f"{email}: demo subject is already there"
        old.deleted_at = now  # an earlier seed without an indexed textbook: set aside, redo
    day = learning_day(now, ZoneInfo(user.timezone), user.day_start_hour)
    subject, _ = subjects.create_with_exam(DEMO_SUBJECT, day + timedelta(days=30))
    _fill(session, user, subject.id, now, day)
    session.flush()
    return (
        f"{email}: demo subject created with {len(_CARDS)} due cards and {len(_PRACTICE)} questions"
    )


def _fill(session: Session, user: User, subject_id: uuid.UUID, now: datetime, day: date) -> None:
    uid = user.id
    sha = hashlib.sha256(f"demo-{uid}".encode()).hexdigest()
    doc = Document(
        user_id=uid,
        subject_id=subject_id,
        short_name="Giáo trình mạng máy tính",
        sha256=sha,
        size_bytes=1_000_000,
        object_key=f"users/{uid}/subjects/{subject_id}/raw/{sha}.pdf",
        status="indexed",
        presigned_at=now,
        uploaded_at=now,
        role="textbook",
        format="pdf",
        page_count=130,
        run_id=uuid.uuid4(),
        toc_key=f"derived/demo-{uid}/toc.json",
        page_labels_key=f"derived/demo-{uid}/labels.json",
        page_text_key=f"derived/demo-{uid}/text.json",
        thumbnails_prefix=f"derived/demo-{uid}/thumbs/",
    )
    session.add(doc)
    session.flush()
    sections: list[DocSection] = []  # the leaves, in reading order
    for chapter_index, (chapter_title, leaves) in enumerate(_CHAPTERS):
        chapter = DocSection(
            user_id=uid,
            subject_id=subject_id,
            document_id=doc.id,
            parent_id=None,
            ord=chapter_index,
            title=chapter_title,
            weight=float(sum(last - first + 1 for _, first, last, _ in leaves)),
            studied_weight=float(
                sum(last - first + 1 for _, first, last, studied in leaves if studied)
            ),
            unit="page",
            source="user",
            first_page=leaves[0][1],
            last_page=leaves[-1][2],
        )
        session.add(chapter)
        session.flush()
        for index, (title, first, last, studied) in enumerate(leaves):
            weight = float(last - first + 1)
            leaf = DocSection(
                user_id=uid,
                subject_id=subject_id,
                document_id=doc.id,
                parent_id=chapter.id,
                ord=index,
                title=title,
                weight=weight,
                studied_weight=weight if studied else 0.0,
                unit="page",
                source="user",
                first_page=first,
                last_page=last,
            )
            session.add(leaf)
            sections.append(leaf)
    session.flush()
    study = StudySession(
        user_id=uid,
        subject_id=subject_id,
        description_raw="Buổi học mẫu: TCP, UDP và gói tin.",
        status="confirmed",
        extraction="proposed",
        studied_on=day - timedelta(days=1),
        learning_day=day - timedelta(days=1),
        confirmed_at=now - timedelta(days=1),
        processing_state="processed",
    )
    session.add(study)
    session.flush()
    run_id = uuid.uuid4()
    yesterday = now - timedelta(days=1)
    for title, summary, prompt, answer, section_index in _CARDS:
        unit = KnowledgeUnit(
            user_id=uid,
            subject_id=subject_id,
            title=title,
            summary=summary,
            kind="concept",
            status="canonical",
            run_id=run_id,
            session_id=study.id,
            saved_at=yesterday,
            saved_learning_day=day - timedelta(days=1),
        )
        session.add(unit)
        session.flush()
        session.add(
            UnitSection(
                user_id=uid,
                subject_id=subject_id,
                unit_id=unit.id,
                section_id=sections[section_index].id,
            )
        )
        question = Question(
            user_id=uid,
            subject_id=subject_id,
            level=1,
            prompt=prompt,
            reference_answer=answer,
            status="active",
            content_hash=content_hash(prompt),
            run_id=run_id,
            source="review_auto",
            quality_status="ok",
            unit_rev=0,
        )
        session.add(question)
        session.flush()
        session.add(
            QuestionUnit(
                user_id=uid, subject_id=subject_id, question_id=question.id, unit_id=unit.id
            )
        )
        session.add(
            MemoryState(
                user_id=uid,
                unit_id=unit.id,
                facet="core",
                phase="review",
                step=None,
                stability=3.0,
                difficulty=5.0,
                due=now - timedelta(hours=2),
                last_review=now - timedelta(days=3),
            )
        )
    for prompt, answer, section_index in _PRACTICE:
        question = Question(
            user_id=uid,
            subject_id=subject_id,
            level=2,
            prompt=prompt,
            reference_answer=answer,
            status="active",
            content_hash=content_hash(prompt),
            source="bank",
            quality_status="ok",
        )
        session.add(question)
        session.flush()
        session.add(
            QuestionSection(
                user_id=uid,
                subject_id=subject_id,
                question_id=question.id,
                section_id=sections[section_index].id,
            )
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core_api.cli_demo_account")
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args(argv)
    if get_settings().environment not in DEV_ENVIRONMENTS:
        print("cli_demo_account runs only in local and test", file=sys.stderr)
        return 1
    with Session(get_engine()) as session:
        print(seed_account(session, args.email, args.password))
        session.commit()
    print(f"login: {args.email} / {args.password}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
