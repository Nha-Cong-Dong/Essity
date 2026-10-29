"""T3.2: `python -m core_api.cli_export_eval --out FILE` writes attempt + grade + user_override
as JSONL, only for accounts that agreed to their data being used for evals (ADR-0010)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session
from test_t26_rebuild import EXAM, Learner

from core_api.cli_export_eval import run
from core_api.db.models import User
from core_api.domain.scheduling.rating import ReviewRating, Verdict
from core_api.repositories.review import (
    AttemptRepository,
    GradeRepository,
    ReviewSessionRepository,
)

AT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def _reviewed(db_session: Session, user: User, title: str, answer: str) -> Learner:
    learner = Learner(db_session, user)
    unit, question = learner.unit(learner.subject("Mạng"), title)
    sitting = ReviewSessionRepository(db_session, user.id).start(AT.date(), AT)
    attempts = AttemptRepository(db_session, user.id)
    attempt = attempts.create_draft(sitting.id, question.id)
    attempts.save_draft(attempt.id, answer_text=answer, dont_remember=False)
    attempts.submit(attempt.id, AT)
    learner.grade(attempt.id, unit.id, ReviewRating.GOOD, AT, EXAM)
    learner.attempt_id, learner.unit_id = attempt.id, unit.id  # type: ignore[attr-defined]
    return learner


def _export(db_session: Session, tmp_path: Path) -> tuple[int, list[dict[str, Any]]]:
    out = tmp_path / "eval.jsonl"
    status = run(db_session, ["--out", str(out)])
    lines = out.read_text(encoding="utf-8").splitlines() if out.exists() else []
    return status, [json.loads(line) for line in lines]


def test_t32_only_consented_accounts_are_exported(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice, bob = two_users
    alice.eval_consent_at = AT
    _reviewed(db_session, alice, "TCP", "câu trả lời của alice")
    _reviewed(db_session, bob, "UDP", "bí mật của bob")
    db_session.flush()

    status, rows = _export(db_session, tmp_path)

    assert status == 0
    assert [row["answer_text"] for row in rows] == ["câu trả lời của alice"]
    raw = (tmp_path / "eval.jsonl").read_text(encoding="utf-8")
    assert "bí mật của bob" not in raw and "UDP" not in raw
    assert "alice@example.com" not in raw and "bob@example.com" not in raw


def test_t32_nobody_consented_exports_an_empty_file(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    _reviewed(db_session, two_users[1], "UDP", "bí mật của bob")

    status, rows = _export(db_session, tmp_path)

    assert status == 0 and rows == []


def test_t32_revoked_consent_is_excluded(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    _reviewed(db_session, alice, "TCP", "đã từng đồng ý")
    alice.eval_consent_at = None
    db_session.flush()

    assert _export(db_session, tmp_path)[1] == []


def test_t32_deleted_account_is_excluded(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    _reviewed(db_session, alice, "TCP", "tài khoản đã xóa")
    alice.deleted_at = AT
    db_session.flush()

    assert _export(db_session, tmp_path)[1] == []


def test_t32_row_holds_question_answer_and_every_grade_in_order(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    learner = _reviewed(db_session, alice, "TCP", "trả lời")
    GradeRepository(db_session, alice.id).add_with_units(
        learner.attempt_id,  # type: ignore[attr-defined]
        source="user_override",
        overall=Verdict.PARTIAL,
        understanding=1,
        units={learner.unit_id: Verdict.PARTIAL},  # type: ignore[attr-defined]
        run_id=None,
    )
    db_session.flush()

    _, rows = _export(db_session, tmp_path)

    (row,) = rows
    assert row["question"]["prompt"] == "TCP?"
    assert row["question"]["reference_answer"] == "a"
    assert [grade["source"] for grade in row["grades"]] == ["ai", "user_override"]
    assert row["grades"][1]["overall"] == "partial"
    assert row["grades"][1]["units"] == [{"title": "TCP", "verdict": "partial"}]
    assert "user_id" not in row and "email" not in json.dumps(row)


def test_t32_draft_attempts_are_not_exported(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    learner = Learner(db_session, alice)
    _, question = learner.unit(learner.subject("Mạng"), "TCP")
    sitting = ReviewSessionRepository(db_session, alice.id).start(AT.date(), AT)
    AttemptRepository(db_session, alice.id).create_draft(sitting.id, question.id)
    db_session.flush()

    assert _export(db_session, tmp_path)[1] == []


def test_t32_answer_text_never_reaches_the_logs(
    db_session: Session,
    two_users: tuple[User, User],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    _reviewed(db_session, alice, "TCP", "nội dung riêng tư")
    caplog.set_level("DEBUG")

    _export(db_session, tmp_path)

    seen = caplog.text + capsys.readouterr().out + capsys.readouterr().err
    assert "nội dung riêng tư" not in seen
