"""`python -m core_api.cli_review_account --outline FILE [--pdf FILE] [--account-file FILE]`: a
brand-new account for the review build (REVIEW-SEED, 05/11).

One subject, "Xác suất thống kê", with the real textbook outline (`outline.json` from
`scripts/review_seed_outline.py`, parsed by the same rules as an indexing answer) and every state
a reviewer wants to see: cards due today, edges between cards, outline sections studied (chapter 1
in part), practice questions due today, and questions already answered, one of them answered
twice and regraded, so its schedule follows the last attempt. Local and test only.

The password is random and goes to `--account-file` only, never to the log. Run twice, it adds
nothing (the user is found by email; a subject of that name means it is done). No AI call: cards,
questions and grades are written through the repositories and services the app uses.
"""

import argparse
import hashlib
import json
import secrets
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from core_api.clients.storage import ObjectStorage, S3Storage
from core_api.config import DEV_ENVIRONMENTS, get_settings
from core_api.db.engine import get_engine
from core_api.db.models import (
    Anchor,
    DocSection,
    Document,
    KnowledgeUnit,
    MemoryState,
    Question,
    QuestionSection,
    QuestionUnit,
    StudySession,
    UnitEdge,
    UnitSection,
    User,
)
from core_api.domain.auth.passwords import hash_password
from core_api.domain.learning_day import learning_day
from core_api.domain.mastery import PracticeVerdict
from core_api.domain.question_hash import content_hash
from core_api.domain.scheduling.rating import Verdict
from core_api.handlers.document_indexed import parse_outline
from core_api.repositories.practice_attempt import PracticeAttemptRepository
from core_api.repositories.review import GradeRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.user import UserRepository
from core_api.services.outline import OutlineService
from core_api.services.practice import record_grade
from core_api.services.practice_grading import override_practice_grade

REVIEW_EMAIL = "xstk.review@essity.test"
REVIEW_USERNAME = "xstkreview"
REVIEW_SUBJECT = "Xác suất thống kê"
_VERDICT = {"correct": Verdict.CORRECT, "partial": Verdict.PARTIAL, "incorrect": Verdict.INCORRECT}

# Leaves studied, by the number a title starts with. Chapter 1 in part: 1.4.3, 1.4.4 and the
# exercises stay open; chapter 2 is untouched.
_STUDIED = (
    "1.1.1.",
    "1.1.2.",
    "1.1.3.",
    "1.1.4.",
    "1.1.5.",
    "1.1.6.",
    "1.1.7.",
    "1.2.1.",
    "1.2.2.",
    "1.2.3.",
    "1.3.1.",
    "1.3.2.",
    "1.4.1.",
    "1.4.2.",
)


@dataclass(frozen=True)
class _Card:
    title: str
    summary: str
    prompt: str
    answer: str
    section: str  # the number the section's title starts with
    quote: str  # a line of the textbook, as read from the PDF
    page: int
    sitting: int  # which study session saved it (0 = the earlier one)
    due_in_hours: int  # relative to now: negative = already due


CARDS = (
    _Card(
        "Quy tắc cộng mở rộng",
        "Số phần tử của hợp hai tập bằng tổng trừ phần giao.",
        "Quy tắc cộng mở rộng đếm số phần tử của A ∪ B như thế nào?",
        "n(A ∪ B) = n(A) + n(B) − n(A ∩ B): trừ phần giao vì nó bị đếm hai lần.",
        "1.1.1.",
        "n(A ∪ B) = n(A) + n(B) − n(A ∩ B).",
        7,
        0,
        -30,
    ),
    _Card(
        "Quy tắc nhân",
        "Công việc gồm k giai đoạn độc lập thì nhân số cách của từng giai đoạn.",
        "Một công việc có k giai đoạn, giai đoạn i có n_i cách. Có bao nhiêu cách làm xong?",
        "n1 · n2 · … · nk cách (quy tắc nhân).",
        "1.1.2.",
        "Ai được thực hiện bởi 1 trong ni cách, với mọi i = 1, . . . , k. Khi đó, có n1n2 . . . "
        "nk cách thực",
        7,
        0,
        -26,
    ),
    _Card(
        "Chỉnh hợp",
        "Dãy có thứ tự gồm k phần tử khác nhau lấy từ n phần tử.",
        "Chỉnh hợp chập k của n phần tử là gì và có bao nhiêu chỉnh hợp?",
        "Là một dãy có thứ tự gồm k phần tử khác nhau lấy từ tập n phần tử; "
        "có A(n,k) = n!/(n − k)! chỉnh hợp.",
        "1.1.4.",
        "Một chỉnh hợp (arrangement) chập k của n phần tử (0 < k 6 n) là một dãy",
        8,
        0,
        -22,
    ),
    _Card(
        "Chỉnh hợp lặp",
        "Dãy có thứ tự k phần tử không nhất thiết khác nhau: n^k.",
        "Chỉnh hợp lặp chập k của n phần tử khác chỉnh hợp ở chỗ nào?",
        "Các phần tử trong dãy không cần khác nhau; số dãy là n^k.",
        "1.1.5.",
        "Một chỉnh hợp lặp (arrangement with repetition) chập k của n phần tử là",
        8,
        0,
        -18,
    ),
    _Card(
        "Phép thử ngẫu nhiên",
        "Phép thử mà không đoán chắc được kết quả trước khi làm.",
        "Thế nào là một phép thử ngẫu nhiên?",
        "Một thí nghiệm hay quan sát mà ta không thể dự báo chắc chắn kết quả trước.",
        "1.2.1.",
        "không thể dự báo trước được một cách chắc chắn kết quả của nó sẽ như thế nào được gọi là",
        10,
        0,
        -14,
    ),
    _Card(
        "Không gian mẫu và biến cố sơ cấp",
        "Không gian mẫu S là tập mọi kết quả có thể; mỗi phần tử là một biến cố sơ cấp.",
        "Không gian mẫu và biến cố sơ cấp là gì?",
        "Không gian mẫu S là tập hợp mọi kết quả có thể có của phép thử; mỗi phần tử của S "
        "là một biến cố sơ cấp, và mỗi tập con của S là một biến cố ngẫu nhiên.",
        "1.2.2.",
        "Tập hợp gồm tất cả các kết quả có thể có của phép thử được gọi là không",
        10,
        0,
        -10,
    ),
    _Card(
        "Hợp và giao của hai biến cố",
        "A ∪ B xảy ra khi ít nhất một trong hai xảy ra; A ∩ B khi cả hai cùng xảy ra.",
        "Hợp và giao của hai biến cố A, B xảy ra khi nào?",
        "A ∪ B xảy ra khi và chỉ khi ít nhất một trong A, B xảy ra; "
        "A ∩ B xảy ra khi và chỉ khi cả A và B xảy ra.",
        "1.2.3.",
        "Hợp (union) của hai biến cố A và B , ký hiệu bởi A ∪ B , là biến cố xảy ra khi và chỉ",
        11,
        1,
        -6,
    ),
    _Card(
        "Định nghĩa cổ điển của xác suất",
        "P(A) = n(A)/n(S) khi các biến cố sơ cấp đồng khả năng.",
        "Xác suất theo định nghĩa cổ điển được tính như thế nào, và khi nào dùng được?",
        "P(A) = n(A)/n(S), chỉ khi phép thử có các biến cố sơ cấp đồng khả năng.",
        "1.3.1.",
        "Xét phép thử đang quan sát có phải là phép thử đồng khả năng không.",
        14,
        1,
        -4,
    ),
    _Card(
        "Tần suất và định nghĩa thống kê",
        "Xác suất là giới hạn của tần suất f_n(A) = m/n khi n tăng.",
        "Tần suất của biến cố A là gì, và nó liên hệ với xác suất ra sao?",
        "f_n(A) = m/n (m lần A xảy ra trong n phép thử); khi n đủ lớn tần suất ổn định quanh "
        "xác suất của A.",
        "1.3.2.",
        "Tần suất (relative frequency) xuất hiện biến cố A, ký hiệu fn(A), là tỷ số",
        16,
        1,
        -2,
    ),
    _Card(
        "Định lý cộng xác suất",
        "P(A + B) = P(A) + P(B) − P(AB); biến cố xung khắc thì bỏ số hạng cuối.",
        "Định lý cộng xác suất cho hai biến cố bất kỳ phát biểu thế nào?",
        "P(A ∪ B) = P(A) + P(B) − P(AB); nếu A, B xung khắc thì P(AB) = 0.",
        "1.4.1.",
        "P(A + B) = P(A) + P(B) − P(AB) = 0,8 + 0,5 − 0,4 = 0,9.",
        18,
        1,
        -1,
    ),
    _Card(
        "Xác suất có điều kiện",
        "P(A|B) = P(AB)/P(B) với P(B) > 0.",
        "Xác suất có điều kiện của A với giả thiết B đã xảy ra được định nghĩa thế nào?",
        "P(A|B) = P(AB)/P(B), với P(B) > 0.",
        "1.4.2.",
        "Định nghĩa 1.4.5. Giả sử A và B là hai biến cố bất kỳ trong cùng một phép thử sao cho",
        19,
        1,
        30,
    ),
    _Card(
        "P(A|B) khác P(B|A)",
        "Nhìn chung hai xác suất có điều kiện đảo nhau không bằng nhau.",
        "P(A|B) có bằng P(B|A) không?",
        "Nhìn chung không: P(A|B) = P(AB)/P(B) còn P(B|A) = P(AB)/P(A), mẫu số khác nhau.",
        "1.4.2.",
        "Chú ý 1.4.6. Với hai biến cố A,B bất kỳ thì nhìn chung P(A|B) 6= P(B|A). Thật vậy, xét ví",
        19,
        1,
        50,
    ),
)

# (src card, dst card, kind): "prerequisite" reads "source needs target first". Indices into CARDS.
EDGES = (
    (2, 1, "prerequisite"),
    (3, 2, "prerequisite"),
    (3, 1, "prerequisite"),
    (5, 4, "prerequisite"),
    (6, 5, "prerequisite"),
    (7, 6, "prerequisite"),
    (9, 7, "prerequisite"),
    (10, 6, "prerequisite"),
    (9, 8, "contrast"),
    (11, 10, "prerequisite"),
    (7, 3, "example_of"),
    (10, 7, "applies_to"),
    (11, 6, "part_of"),
    (1, 0, "part_of"),
)


@dataclass(frozen=True)
class _Practice:
    prompt: str
    answer: str
    cards: tuple[int, ...]  # the cards it checks (indices of CARDS)
    section: str  # a section it sits under (title number)
    # Attempts oldest first: (days ago, verdict, answer the learner wrote, overridden to)
    history: tuple[tuple[float, PracticeVerdict, str, PracticeVerdict | None], ...] = ()


PRACTICE = (
    # Answered once, wrong a while ago: due today.
    _Practice(
        "Một hội nghị có 100 người biết tiếng Anh, 60 người biết tiếng Pháp, 20 người biết cả "
        "hai và 50 người không biết thứ nào. Hội nghị có bao nhiêu người?",
        "n(A ∪ B) = 100 + 60 − 20 = 140; cộng 50 người còn lại được 190 người.",
        (0,),
        "1.1.1.",
        ((9.0, "incorrect", "100 + 60 + 50 = 210 người.", None),),
    ),
    # Answered twice: wrong, then right a day later; then the learner regraded the second
    # attempt. The schedule follows the last attempt and its latest grade.
    _Practice(
        "Có 5 học phần xếp vào một buổi, mỗi buổi 2 học phần và thứ tự có phân biệt. "
        "Có bao nhiêu cách xếp thời khóa biểu?",
        "Số chỉnh hợp chập 2 của 5: A(5,2) = 5 · 4 = 20 cách.",
        (2,),
        "1.1.4.",
        (
            (8.0, "incorrect", "C(5,2) = 10 cách.", None),
            (5.0, "partial", "Chỉnh hợp 5·4 nhưng chưa nói rõ vì sao.", "correct"),
        ),
    ),
    # Answered right long ago: due today.
    _Practice(
        "Trong chuồng có 6 gà trống và 4 gà mái. Bắt ngẫu nhiên một con. "
        "Xác suất bắt được gà mái là bao nhiêu?",
        "Các biến cố sơ cấp đồng khả năng: P = 4/10 = 0,4.",
        (7,),
        "1.3.1.",
        ((20.0, "correct", "P = 4/10 = 0,4.", None),),
    ),
    # Answered right yesterday: not due yet.
    _Practice(
        "Chồng xem tivi với xác suất 0,8, vợ 0,5, cả hai 0,4. Xác suất tivi có người xem?",
        "P(A + B) = 0,8 + 0,5 − 0,4 = 0,9.",
        (9,),
        "1.4.1.",
        ((1.0, "correct", "0,8 + 0,5 − 0,4 = 0,9.", None),),
    ),
    # Never answered: ready, and due today (a candidate).
    _Practice(
        "Tần suất và xác suất của một biến cố khác nhau ở điểm nào?",
        "Tần suất tính trên n phép thử đã làm và thay đổi theo n; xác suất là giá trị mà tần "
        "suất ổn định quanh khi n đủ lớn.",
        (8,),
        "1.3.2.",
    ),
    _Practice(
        "Chứng tỏ P(A|B) nhìn chung khác P(B|A) bằng một ví dụ gieo xúc xắc.",
        "P(A|B) = P(AB)/P(B) và P(B|A) = P(AB)/P(A); khi P(A) ≠ P(B) hai giá trị khác nhau.",
        (11,),
        "1.4.2.",
    ),
    # Waits for a section not studied yet (Bayes, 1.4.3).
    _Practice(
        "Phát biểu định lý xác suất toàn phần và nêu một ví dụ.",
        "P(A) = Σ P(E_i) P(A|E_i) với E_i là một hệ đầy đủ các biến cố.",
        (10,),
        "1.4.3.",
    ),
)


def seed_account(
    session: Session,
    outline_raw: bytes,
    now: datetime | None = None,
    *,
    email: str = REVIEW_EMAIL,
    username: str = REVIEW_USERNAME,
    password: str | None = None,
    pdf: bytes | None = None,
    storage: ObjectStorage | None = None,
) -> tuple[str, str | None]:
    """Make the account once. Returns a line to print and the password when this call made the
    user (None when it was already there)."""
    now = now or datetime.now(UTC)
    users = UserRepository(session)
    user = users.get_by_email(email)
    chosen: str | None = None
    if user is None:
        chosen = password or secrets.token_urlsafe(12)
        user = users.create(email, password_hash=hash_password(chosen), username=username)
        user.email_verified_at = now
        session.flush()
    subjects = SubjectRepository(session, user.id)
    if any(s.name == REVIEW_SUBJECT for s, _, _ in subjects.list_with_exams()):
        return f"{email}: review subject is already there", None
    day = learning_day(now, ZoneInfo(user.timezone), user.day_start_hour)
    subject, _ = subjects.create_with_exam(REVIEW_SUBJECT, day + timedelta(days=40))
    _fill(session, user, subject.id, outline_raw, now, day, pdf, storage)
    session.flush()
    return (
        f"{email}: review subject created with {len(CARDS)} cards, {len(EDGES)} edges and "
        f"{len(PRACTICE)} practice questions",
        chosen,
    )


def _sha(user: User, pdf: bytes | None) -> str:
    return hashlib.sha256(pdf or f"review-{user.id}".encode()).hexdigest()


def _fill(
    session: Session,
    user: User,
    subject_id: uuid.UUID,
    outline_raw: bytes,
    now: datetime,
    day: date,
    pdf: bytes | None,
    storage: ObjectStorage | None,
) -> None:
    uid = user.id
    last_page = max(int(n["page_end"]) for n in json.loads(outline_raw)["nodes"])
    page_count = last_page
    parsed = parse_outline(outline_raw, page_count)
    assert parsed is not None, "the outline file breaks the indexing rules"
    sha = _sha(user, pdf)
    doc = Document(
        user_id=uid,
        subject_id=subject_id,
        short_name="Giáo trình Xác suất thống kê",
        sha256=sha,
        size_bytes=len(pdf) if pdf else 1_000_000,
        object_key=f"users/{uid}/subjects/{subject_id}/raw/{sha}.pdf",
        status="indexed",
        presigned_at=now,
        uploaded_at=now,
        role="textbook",
        format="pdf",
        page_count=page_count,
        run_id=uuid.uuid4(),
        toc_key=f"derived/review-{uid}/toc.json",
        page_labels_key=f"derived/review-{uid}/labels.json",
        page_text_key=f"derived/review-{uid}/text.json",
        thumbnails_prefix=f"derived/review-{uid}/thumbs/",
    )
    session.add(doc)
    session.flush()
    if pdf is not None and storage is not None:
        storage.write(doc.object_key, pdf, content_type="application/pdf")
    outline = OutlineService(session, uid)
    assert outline.store_outline(doc, parsed[1])
    session.flush()
    sections = {
        s.title.split(" ", 1)[0]: s for s in outline.sections.of_document(doc.id) if s.title
    }
    for number in _STUDIED:
        outline.edit_section(sections[number].id, studied=True)
    session.flush()

    sittings = [
        _sitting(session, uid, subject_id, now, day, 6, "Buổi học: giải tích tổ hợp và biến cố."),
        _sitting(
            session, uid, subject_id, now, day, 2, "Buổi học: xác suất và xác suất có điều kiện."
        ),
    ]
    units = [
        _card(session, uid, subject_id, doc, sections, card, sittings[card.sitting], now)
        for card in CARDS
    ]
    for src, dst, kind in EDGES:
        a, b = units[src], units[dst]
        if kind == "contrast" and a > b:  # stored one way only
            a, b = b, a
        session.add(
            UnitEdge(
                user_id=uid,
                subject_id=subject_id,
                src_unit_id=a,
                dst_unit_id=b,
                kind=kind,
                origin="user",
                status="active",
                evidence=[],
            )
        )
    session.flush()
    for item in PRACTICE:
        _practice(session, user, subject_id, sections, units, item, now)


def _sitting(
    session: Session,
    uid: uuid.UUID,
    subject_id: uuid.UUID,
    now: datetime,
    day: date,
    days_ago: int,
    text: str,
) -> StudySession:
    sitting = StudySession(
        user_id=uid,
        subject_id=subject_id,
        description_raw=text,
        status="confirmed",
        extraction="proposed",
        studied_on=day - timedelta(days=days_ago),
        learning_day=day - timedelta(days=days_ago),
        confirmed_at=now - timedelta(days=days_ago),
        processing_state="processed",
    )
    session.add(sitting)
    session.flush()
    return sitting


def _card(
    session: Session,
    uid: uuid.UUID,
    subject_id: uuid.UUID,
    doc: Document,
    sections: dict[str, DocSection],
    card: _Card,
    sitting: StudySession,
    now: datetime,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    saved = sitting.confirmed_at or now
    unit = KnowledgeUnit(
        user_id=uid,
        subject_id=subject_id,
        title=card.title,
        summary=card.summary,
        kind="concept",
        status="canonical",
        run_id=run_id,
        session_id=sitting.id,
        saved_at=saved,
        saved_learning_day=sitting.learning_day,
    )
    session.add(unit)
    session.flush()
    session.add(
        UnitSection(
            user_id=uid,
            subject_id=subject_id,
            unit_id=unit.id,
            section_id=sections[card.section].id,
        )
    )
    # Grading needs one source quote per card (grading.build_request); these are lines of the PDF.
    session.add(
        Anchor(
            user_id=uid,
            unit_id=unit.id,
            source="document",
            document_id=doc.id,
            page_no=card.page,
            quote_text=card.quote,
            run_id=run_id,
        )
    )
    question = Question(
        user_id=uid,
        subject_id=subject_id,
        level=1,
        prompt=card.prompt,
        reference_answer=card.answer,
        status="active",
        content_hash=content_hash(card.prompt),
        run_id=run_id,
        source="review_auto",
        quality_status="ok",
        unit_rev=0,
    )
    session.add(question)
    session.flush()
    session.add(
        QuestionUnit(user_id=uid, subject_id=subject_id, question_id=question.id, unit_id=unit.id)
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
            due=now + timedelta(hours=card.due_in_hours),
            last_review=saved,
        )
    )
    return unit.id


def _practice(
    session: Session,
    user: User,
    subject_id: uuid.UUID,
    sections: dict[str, DocSection],
    units: list[uuid.UUID],
    item: _Practice,
    now: datetime,
) -> None:
    uid = user.id
    question = Question(
        user_id=uid,
        subject_id=subject_id,
        level=2,
        prompt=item.prompt,
        reference_answer=item.answer,
        status="active",
        content_hash=content_hash(item.prompt),
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
            section_id=sections[item.section].id,
        )
    )
    linked = [units[i] for i in item.cards]
    for unit_id in linked:
        session.add(
            QuestionUnit(
                user_id=uid, subject_id=subject_id, question_id=question.id, unit_id=unit_id
            )
        )
    session.flush()
    attempts = PracticeAttemptRepository(session, uid)
    grades = GradeRepository(session, uid)
    for days_ago, verdict, written, overridden in item.history:
        at = now - timedelta(days=days_ago)
        draft, _ = attempts.open_draft(question.id, at - timedelta(seconds=90))
        attempt = attempts.submit(
            draft.id, at, hidden_ms=0, reference_seconds=100.0, answer_text=written
        )
        grade = grades.add_with_units(
            attempt.id,
            source="ai",
            overall=_VERDICT[verdict],
            understanding=None,
            units={unit_id: _VERDICT[verdict] for unit_id in linked},
            run_id=None,
        )
        session.flush()
        record_grade(
            session,
            uid,
            question.id,
            grade.id,
            verdict=verdict,
            active_seconds=60.0,
            reference_seconds=100.0,
            timing_ok=True,
        )
        if overridden is not None and overridden != verdict:
            # "Chấm sai" on the web: a new grade of this attempt, the log gets a row, the
            # schedule is rebuilt from the effective ratings (US-16 AC10).
            assert overridden in ("correct", "incorrect")
            override_practice_grade(session, uid, grade.id, overridden)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core_api.cli_review_account")
    parser.add_argument("--outline", required=True, type=Path, help="outline.json of the textbook")
    parser.add_argument("--pdf", type=Path, help="the textbook PDF, uploaded to storage")
    parser.add_argument("--account-file", type=Path, help="where the login is written")
    parser.add_argument("--email", default=REVIEW_EMAIL)
    args = parser.parse_args(argv)
    if get_settings().environment not in DEV_ENVIRONMENTS:
        print("cli_review_account runs only in local and test", file=sys.stderr)
        return 1
    pdf = args.pdf.read_bytes() if args.pdf else None
    with Session(get_engine()) as session:
        storage = S3Storage.from_settings(get_settings()) if pdf else None
        line, password = seed_account(
            session, args.outline.read_bytes(), email=args.email, pdf=pdf, storage=storage
        )
        session.commit()
    print(line)
    if password is not None and args.account_file is not None:
        args.account_file.write_text(f"{args.email}\n{password}\n", encoding="utf-8")
        print(f"login written to {args.account_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
