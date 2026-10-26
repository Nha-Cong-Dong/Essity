"""T2.2: `python -m core_api.cli_seed seed-questions --user-email … --subject … file.yaml` loads
one chapter of hand-written units and questions (no spec: a phase-1 script, not a user story)."""

import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.cli_seed import run
from core_api.db.models import Anchor, KnowledgeUnit, Question, QuestionUnit, User
from core_api.repositories.subject import SubjectRepository

EXAMPLE = Path(__file__).resolve().parents[3] / "data" / "seed" / "example.yaml"

VALID = """\
units:
  - title: Bắt tay ba bước
    summary: TCP mở kết nối bằng SYN, SYN-ACK, ACK.
    kind: concept
    sources:
      - source: document
        page: 4
        quote: TCP thiết lập kết nối bằng bắt tay ba bước.
      - source: notes
        quote: Nhớ thứ tự SYN rồi SYN-ACK.
  - title: UDP
    summary: Không kết nối.
    kind: concept
    sources:
      - source: document
        quote: UDP không thiết lập kết nối.
questions:
  - level: 1
    prompt: TCP mở kết nối thế nào?
    answer: Bắt tay ba bước.
    units: [Bắt tay ba bước]
  - level: 2
    prompt: So sánh TCP và UDP khi mở kết nối.
    answer: TCP bắt tay, UDP không.
    units: [Bắt tay ba bước, UDP]
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "seed.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def subject_of(session: Session, user: User) -> uuid.UUID:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", date(2027, 1, 20))
    return subject.id


def seed(session: Session, user: User, subject_id: uuid.UUID, path: Path, *extra: str) -> int:
    argv = ["seed-questions", "--user-email", user.email, "--subject", str(subject_id)]
    return run(session, [*argv, *extra, str(path)])


def counts(session: Session, user: User) -> tuple[int, int, int, int]:
    def count(model: type[KnowledgeUnit] | type[Question] | type[QuestionUnit] | type[Anchor]):
        return session.scalar(select(func.count()).where(model.user_id == user.id)) or 0

    return count(KnowledgeUnit), count(Anchor), count(Question), count(QuestionUnit)


# Red when: the loader drops units, sources, questions or their links.
def test_t22_seed_loads_units_sources_questions_and_links(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    assert seed(db_session, alice, subject_id, write(tmp_path, VALID)) == 0
    assert counts(db_session, alice) == (2, 3, 2, 3)


# Red when: a second run adds a duplicate question, unit, source or link ("xong khi").
def test_t22_seed_twice_adds_nothing(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    path = write(tmp_path, VALID)
    assert seed(db_session, alice, subject_id, path) == 0
    first = counts(db_session, alice)
    assert seed(db_session, alice, subject_id, path) == 0
    assert counts(db_session, alice) == first


# Red when: the same prompt typed with other spacing is added as a second question.
def test_t22_seed_a_reflowed_prompt_is_the_same_question(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    seed(db_session, alice, subject_id, write(tmp_path, VALID))
    reflowed = VALID.replace("TCP mở kết nối thế nào?", "TCP  mở kết nối   thế nào?")
    assert seed(db_session, alice, subject_id, write(tmp_path, reflowed)) == 0
    assert counts(db_session, alice)[2] == 2


# Red when: every question of a file gets a new run_id, so a re-run is not one "bản seed".
def test_t22_seed_uses_one_fixed_run_id(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    seed(db_session, alice, subject_id, write(tmp_path, VALID))
    runs = set(db_session.scalars(select(Question.run_id).where(Question.user_id == alice.id)))
    runs |= set(db_session.scalars(select(KnowledgeUnit.run_id)))
    assert len(runs) == 1


@pytest.mark.parametrize(
    ("text", "line", "word"),
    [
        (VALID.replace("level: 1", "level: 7"), 18, "level"),
        (VALID.replace("kind: concept", "kind: idea", 1), 4, "kind"),
    ],
)
# Red when: a bad file is reported without the line, or half of it is written.
def test_t22_seed_a_bad_file_names_the_line_and_writes_nothing(
    db_session: Session,
    two_users: tuple[User, User],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    text: str,
    line: int,
    word: str,
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    assert seed(db_session, alice, subject_id, write(tmp_path, text)) == 1
    err = capsys.readouterr().err
    assert f"line {line}" in err and word in err
    assert counts(db_session, alice) == (0, 0, 0, 0)


# Red when: a question names a unit the file does not define, or YAML itself is broken.
def test_t22_seed_unknown_unit_and_broken_yaml_are_refused(
    db_session: Session,
    two_users: tuple[User, User],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    unknown = VALID.replace("units: [Bắt tay ba bước]\n", "units: [Không có]\n", 1)
    assert seed(db_session, alice, subject_id, write(tmp_path, unknown)) == 1
    assert "Không có" in capsys.readouterr().err
    assert seed(db_session, alice, subject_id, write(tmp_path, "units: [\n")) == 1
    assert "line" in capsys.readouterr().err
    assert counts(db_session, alice) == (0, 0, 0, 0)


# Red when: a soft-deleted subject takes questions (T2.3b), or one user seeds into another's.
def test_t22_seed_refuses_a_deleted_subject_and_someone_elses(
    db_session: Session,
    two_users: tuple[User, User],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alice, bob = two_users
    subject_id = subject_of(db_session, alice)
    path = write(tmp_path, VALID)
    assert seed(db_session, bob, subject_id, path) == 1
    assert "subject" in capsys.readouterr().err
    from datetime import UTC, datetime

    SubjectRepository(db_session, alice.id).soft_delete(subject_id, datetime.now(UTC))
    assert seed(db_session, alice, subject_id, path) == 1
    assert counts(db_session, alice) == (0, 0, 0, 0) and counts(db_session, bob)[2] == 0


# Red when: the example file shipped with the repo stops loading.
def test_t22_the_example_file_loads(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, _ = two_users
    subject_id = subject_of(db_session, alice)
    assert seed(db_session, alice, subject_id, EXAMPLE) == 0
    assert counts(db_session, alice)[2] >= 2
