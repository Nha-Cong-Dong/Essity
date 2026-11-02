"""T9.7: `python -m core_api.cli_export_eval --kind unit-edits` writes the learner's rev-1 edit of a
draft card next to the AI's rev 0 (the label of the draft_units eval), only for accounts with
`eval_consent_at` (ADR-0010)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from core_api.cli_export_eval import run
from core_api.db.models import Anchor, UnitRevision, User
from v2_rows import RUN, make_subject, make_unit

AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def _edited(
    db: Session, user: User, title: str, edited: str, *, rev1: bool = True, **unit: Any
) -> None:
    subject = make_subject(db, user, f"Môn {title}")
    card = make_unit(db, user, subject, title=title, status="canonical", **unit)
    ai = {"title": title, "content": "bản của AI", "kind": "concept"}
    db.add(UnitRevision(user_id=user.id, unit_id=card.id, rev=0, origin="ai", content=ai))
    if rev1:
        mine = {"title": title, "content": edited, "kind": "concept"}
        db.add(UnitRevision(user_id=user.id, unit_id=card.id, rev=1, origin="user", content=mine))
    db.add(
        Anchor(
            user_id=user.id,
            unit_id=card.id,
            source="notes",
            quote_text=f"trích của {title}",
            run_id=RUN,
        )
    )
    db.flush()


def _export(db: Session, tmp_path: Path) -> tuple[int, list[dict[str, Any]], str]:
    out = tmp_path / "edits.jsonl"
    status = run(db, ["--kind", "unit-edits", "--out", str(out)])
    raw = out.read_text(encoding="utf-8")
    return status, [json.loads(line) for line in raw.splitlines()], raw


def test_t97_only_consented_accounts_are_exported(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice, bob = two_users
    alice.eval_consent_at = AT
    _edited(db_session, alice, "TCP", "sửa của alice")
    _edited(db_session, bob, "UDP", "bí mật của bob")
    db_session.flush()

    status, rows, raw = _export(db_session, tmp_path)

    assert status == 0
    assert [row["rev1"]["content"] for row in rows] == ["sửa của alice"]
    assert "bí mật của bob" not in raw and "UDP" not in raw
    assert "alice@example.com" not in raw and "bob@example.com" not in raw


@pytest.mark.parametrize("state", ["revoked", "deleted"])
def test_t97_revoked_or_deleted_accounts_are_excluded(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path, state: str
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    _edited(db_session, alice, "TCP", "đã đồng ý")
    if state == "revoked":
        alice.eval_consent_at = None
    else:
        alice.deleted_at = AT
    db_session.flush()

    assert _export(db_session, tmp_path)[1] == []


def test_t97_nobody_consented_exports_an_empty_file(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    _edited(db_session, two_users[1], "UDP", "bí mật của bob")

    assert _export(db_session, tmp_path)[1] == []


def test_t97_row_pairs_ai_draft_with_learner_edit_and_anchors(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    _edited(db_session, alice, "TCP", "sửa")

    (row,) = _export(db_session, tmp_path)[1]

    assert row["rev0"] == {"title": "TCP", "content": "bản của AI", "kind": "concept"}
    assert row["rev1"] == {"title": "TCP", "content": "sửa", "kind": "concept"}
    assert row["anchors"] == ["trích của TCP"]
    assert set(row) == {"unit_id", "rev0", "rev1", "anchors"}


def test_t97_unit_without_a_learner_edit_is_not_exported(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    _edited(db_session, alice, "TCP", "-", rev1=False)

    assert _export(db_session, tmp_path)[1] == []


def test_t97_text_never_reaches_the_logs(
    db_session: Session,
    two_users: tuple[User, User],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    _edited(db_session, alice, "TCP", "nội dung riêng tư")
    caplog.set_level("DEBUG")

    _export(db_session, tmp_path)

    seen = caplog.text + capsys.readouterr().out
    assert "nội dung riêng tư" not in seen and "trích của TCP" not in seen


def test_t97_default_kind_is_still_attempts(
    db_session: Session, two_users: tuple[User, User], tmp_path: Path
) -> None:
    alice = two_users[0]
    alice.eval_consent_at = AT
    _edited(db_session, alice, "TCP", "sửa")
    out = tmp_path / "a.jsonl"

    assert run(db_session, ["--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == ""  # no attempts: the unit edits stay out
