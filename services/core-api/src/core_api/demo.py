"""Made-up study material for trying a review session by hand with the fake grader (T2.16, plan
D-10). Local and test only: `core_api.cli seed-demo` refuses anywhere else."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from core_api.db.models import User
from core_api.domain.learning_day import learning_day
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import AnchorRepository, KnowledgeUnitRepository

DEMO_SUBJECT = "Mạng máy tính (demo)"
EXAM_IN_DAYS = 30


@dataclass(frozen=True)
class _Source:
    kind: str  # "document" or "notes"
    quote: str
    page: int | None


@dataclass(frozen=True)
class _Unit:
    title: str
    summary: str
    sources: tuple[_Source, ...]


@dataclass(frozen=True)
class _Question:
    level: int
    prompt: str
    reference: str
    units: tuple[str, ...]


_UNITS = (
    _Unit(
        "Bắt tay ba bước TCP",
        "TCP mở kết nối bằng SYN, SYN-ACK, ACK.",
        (
            _Source(
                "document", "TCP thiết lập kết nối bằng bắt tay ba bước: SYN, SYN-ACK, ACK.", 47
            ),
        ),
    ),
    _Unit(
        "Timeout và gửi lại",
        "Gói bị mất thì bên gửi chờ hết timeout rồi gửi lại.",
        (
            _Source(
                "document",
                "Nếu SYN-ACK bị mất, client hết timeout thì gửi lại SYN; server ở trạng thái "
                "SYN-RECEIVED gửi lại SYN-ACK.",
                48,
            ),
            _Source("notes", "SYN gửi lại sau 1 s, 2 s, 4 s rồi bỏ.", None),
        ),
    ),
    _Unit(
        "UDP không kết nối",
        "UDP gửi ngay, không bảo đảm gói tới nơi.",
        (_Source("document", "UDP không thiết lập kết nối và không bảo đảm gói tin đến nơi.", 52),),
    ),
)

_QUESTIONS = (
    _Question(
        1,
        "TCP thiết lập kết nối như thế nào?",
        "Bằng bắt tay ba bước: client gửi SYN, server trả SYN-ACK, client gửi ACK.",
        ("Bắt tay ba bước TCP",),
    ),
    _Question(
        2,
        "Gói SYN-ACK trong quá trình bắt tay ba bước bị mất. Client và server sẽ làm gì tiếp theo?",
        "Client hết timeout thì gửi lại SYN; server ở SYN-RECEIVED gửi lại SYN-ACK. Hết số lần "
        "thử thì huỷ kết nối.",
        ("Bắt tay ba bước TCP", "Timeout và gửi lại"),
    ),
    _Question(
        1,
        "Vì sao UDP nhanh hơn TCP nhưng kém tin cậy hơn?",
        "UDP không bắt tay và không gửi lại gói mất, nên ít trễ hơn nhưng không bảo đảm gói "
        "tới nơi.",
        ("UDP không kết nối",),
    ),
)


def seed_demo(session: Session, user: User, now: datetime | None = None) -> int:
    """Adds the demo subject to `user` once, in the caller's transaction. Returns the number of
    questions added: 0 when the user already has it."""
    subjects = SubjectRepository(session, user.id)
    if any(subject.name == DEMO_SUBJECT for subject, _, _ in subjects.list_with_exams()):
        return 0
    day = learning_day(now or datetime.now(UTC), ZoneInfo(user.timezone), user.day_start_hour)
    subject, _ = subjects.create_with_exam(DEMO_SUBJECT, day + timedelta(days=EXAM_IN_DAYS))
    run_id = uuid.uuid4()
    units = KnowledgeUnitRepository(session, user.id)
    anchors = AnchorRepository(session, user.id)
    unit_ids: dict[str, uuid.UUID] = {}
    for spec in _UNITS:
        unit = units.create(
            subject.id, title=spec.title, summary=spec.summary, kind="concept", run_id=run_id
        )
        unit_ids[spec.title] = unit.id
        for source in spec.sources:
            anchors.create(
                unit.id,
                source=source.kind,
                quote_text=source.quote,
                page_no=source.page,
                run_id=run_id,
            )
    questions = QuestionRepository(session, user.id)
    links = QuestionUnitRepository(session, user.id)
    for spec in _QUESTIONS:
        question = questions.add_idempotent(
            subject.id,
            level=spec.level,
            prompt=spec.prompt,
            reference_answer=spec.reference,
            run_id=run_id,
        )
        for title in spec.units:
            links.link(question.id, unit_ids[title])
    session.flush()
    return len(_QUESTIONS)
