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
from sqlalchemy.orm import Session

from core_api.db.engine import get_engine
from core_api.db.models import Attempt, Grade, GradeUnit, KnowledgeUnit, Question, User


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m core_api.cli_export_eval")
    parser.add_argument("--out", required=True, type=Path, help="JSONL file to write")
    return parser


def run(session: Session, argv: Sequence[str]) -> int:
    args = _parser().parse_args(argv)
    count = 0
    with args.out.open("w", encoding="utf-8", newline="\n") as file:
        for row in export_rows(session):
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    print(f"exported {count} attempts to {args.out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    with Session(get_engine()) as session:
        return run(session, sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
