"""`python -m core_api.cli_export_eval --out FILE.jsonl` (T3.2).

Writes the submitted attempts of accounts that agreed to their data being used for evals
(`user.eval_consent_at`, ADR-0010), one JSON line each: the question, the answer, and every
grade of the attempt in order (the AI's, then a `user_override` if the user changed it). The
file is the raw material for labelling the grading eval set (T3.2, us-05).

The consent test is in the SQL of both queries, never applied after loading: a row of an
account that has not agreed (or has withdrawn, or is deleted) is never read. Lines carry no
user id or email, only the attempt's own id. Nothing is logged: ADR-0013, an answer's text
stays out of logs.
"""

import argparse
import json
import sys
import uuid
from collections import defaultdict
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from core_api.db.engine import get_engine
from core_api.db.models import (
    Anchor,
    Attempt,
    Grade,
    GradeUnit,
    KnowledgeUnit,
    Question,
    UnitRevision,
    User,
)


def _consented() -> tuple[Any, ...]:
    return (User.eval_consent_at.is_not(None), User.deleted_at.is_(None))


def _units(session: Session) -> dict[uuid.UUID, list[dict[str, str]]]:
    """Per grade: the verdict on each unit, by the unit's title."""
    rows = session.execute(
        select(GradeUnit.grade_id, KnowledgeUnit.title, GradeUnit.verdict)
        .join(Grade, Grade.id == GradeUnit.grade_id)
        .join(User, User.id == Grade.user_id)
        .join(KnowledgeUnit, KnowledgeUnit.id == GradeUnit.unit_id)
        .where(*_consented())
        .order_by(GradeUnit.grade_id, KnowledgeUnit.title)
    )
    units: dict[uuid.UUID, list[dict[str, str]]] = defaultdict(list)
    for grade_id, title, verdict in rows:
        units[grade_id].append({"title": title, "verdict": verdict})
    return units


def _grades(session: Session) -> dict[uuid.UUID, list[dict[str, Any]]]:
    units = _units(session)
    rows = session.execute(
        select(Grade)
        .join(User, User.id == Grade.user_id)
        .where(*_consented())
        .order_by(Grade.attempt_id, Grade.seq)
    ).scalars()
    grades: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for grade in rows:
        grades[grade.attempt_id].append(
            {
                "source": grade.source,
                "overall": grade.overall,
                "understanding": grade.understanding,
                "missing": grade.missing,
                "units": units.get(grade.id, []),
            }
        )
    return grades


def export_rows(session: Session) -> Iterator[dict[str, Any]]:
    grades = _grades(session)
    attempts = session.execute(
        select(Attempt, Question)
        .join(User, User.id == Attempt.user_id)
        .join(Question, Question.id == Attempt.question_id)
        # A practice attempt has no units or anchors to label (T8.4); its eval set is separate.
        .where(*_consented(), Attempt.status == "submitted", Attempt.review_session_id.is_not(None))
        .order_by(Attempt.submitted_at, Attempt.id)
    )
    for attempt, question in attempts:
        yield {
            "attempt_id": str(attempt.id),
            "question": {
                "level": question.level,
                "prompt": question.prompt,
                "reference_answer": question.reference_answer,
                "rubric": question.rubric,
            },
            "answer_text": attempt.answer_text,
            "dont_remember": attempt.dont_remember,
            "grades": grades.get(attempt.id, []),
        }


def export_unit_edits(session: Session) -> Iterator[dict[str, Any]]:
    """T9.7: the learner's first edit of a card (rev 1, origin user) beside what the AI drafted
    (rev 0) and the quotes the card anchors: the label of the `draft_units` eval. Same consent
    test in the SQL as above; rows carry the unit's own id only."""
    first = aliased(UnitRevision)
    rows = session.execute(
        select(KnowledgeUnit.id, UnitRevision.content, first.content)
        .join(User, User.id == KnowledgeUnit.user_id)
        .join(UnitRevision, UnitRevision.unit_id == KnowledgeUnit.id)
        .join(first, first.unit_id == KnowledgeUnit.id)
        .where(
            *_consented(),
            UnitRevision.rev == 0,
            UnitRevision.origin == "ai",
            first.rev == 1,
            first.origin == "user",
        )
        .order_by(KnowledgeUnit.created_at, KnowledgeUnit.id)
    ).all()
    quotes: dict[uuid.UUID, list[str]] = defaultdict(list)
    for unit_id, quote in session.execute(
        select(Anchor.unit_id, Anchor.quote_text)
        .join(User, User.id == Anchor.user_id)
        .where(*_consented(), Anchor.unit_id.in_([row[0] for row in rows]))
        .order_by(Anchor.unit_id, Anchor.created_at, Anchor.id)
    ):
        quotes[unit_id].append(quote)
    for unit_id, rev0, rev1 in rows:
        yield {
            "unit_id": str(unit_id),
            "rev0": rev0,
            "rev1": rev1,
            "anchors": quotes.get(unit_id, []),
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m core_api.cli_export_eval")
    parser.add_argument(
        "--kind",
        choices=["attempts", "unit-edits"],
        default="attempts",
        help="attempts: grading eval (T3.2); unit-edits: draft_units labels (T9.7)",
    )
    parser.add_argument("--out", required=True, type=Path, help="JSONL file to write")
    return parser


def run(session: Session, argv: Sequence[str]) -> int:
    args = _parser().parse_args(argv)
    count = 0
    with args.out.open("w", encoding="utf-8", newline="\n") as file:
        rows = export_unit_edits if args.kind == "unit-edits" else export_rows
        for row in rows(session):
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    print(f"exported {count} {args.kind} to {args.out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    with Session(get_engine()) as session:
        return run(session, sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
