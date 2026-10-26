"""`python -m core_api.cli_seed seed-questions --user-email EMAIL --subject ID FILE.yaml` (T2.2).

Loads one chapter of hand-written units, sources and questions into a subject of one user, for
phase 1 (questions are seeded by hand until documents arrive in M4). The file is checked whole
first (`seed_file.py`, errors name the line); then everything is written in one transaction, so
a failure leaves nothing behind. Run twice, it adds nothing: a unit is the subject's unit of the
same title, a question the one with the same content hash (`domain.question_hash`).

The file may hold private study material: it stays out of the repository (`data/seed/*` is
ignored, only `example.yaml` is committed).
"""

import argparse
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from core_api.db.engine import get_engine
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.subject import SubjectNotFoundError
from core_api.repositories.unit import AnchorRepository, KnowledgeUnitRepository
from core_api.repositories.user import UserRepository
from core_api.seed_file import SeedFile, SeedFileError, parse

# One fixed run for every seed (plan: "run_id cố định cho bản seed"): the pipeline run that
# stands for "written by hand", in the ai database there is none.
SEED_RUN_ID = uuid.UUID("5eed5eed-5eed-4eed-8eed-5eed5eed5eed")


class SeedError(ValueError):
    """The file cannot be loaded; `problems` are lines ready to print."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Seeded:
    added: int
    replaced: int
    retired: int  # questions of the file the user dropped: left as they are


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m core_api.cli_seed")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed-questions", help="load a seed file into one user's subject")
    seed.add_argument("--user-email", required=True)
    seed.add_argument("--subject", required=True, type=uuid.UUID, help="the subject's id")
    seed.add_argument(
        "--replace-changed",
        action="store_true",
        help="a question whose level or answer differs from the one seeded replaces it: the old "
        "one is retired (its history stays) and a new one takes its place",
    )
    seed.add_argument("file", type=Path)
    return parser


def apply(
    session: Session,
    user_id: uuid.UUID,
    subject_id: uuid.UUID,
    seed: SeedFile,
    *,
    replace_changed: bool = False,
) -> Seeded:
    """Write the file into the subject. A question already there with the same level and answer
    is left; one that differs is a SeedError naming its line, unless `replace_changed`; one the
    user retired is skipped, never brought back. SeedError leaves it to the caller to roll back."""
    units = KnowledgeUnitRepository(session, user_id)
    anchors = AnchorRepository(session, user_id)
    questions = QuestionRepository(session, user_id)
    links = QuestionUnitRepository(session, user_id)
    unit_ids: dict[str, uuid.UUID] = {}
    for spec in seed.units:
        unit = units.find_by_title(subject_id, spec.title) or units.create(
            subject_id,
            title=spec.title,
            summary=spec.summary,
            kind=spec.kind,
            run_id=SEED_RUN_ID,
        )
        unit_ids[spec.title] = unit.id
        for source in spec.sources:
            if not anchors.has_quote(unit.id, source.source, source.quote):
                anchors.create(
                    unit.id,
                    source=source.source,
                    quote_text=source.quote,
                    page_no=source.page,
                    run_id=SEED_RUN_ID,
                )
    added = replaced = retired = 0
    changed: list[str] = []
    for index, spec in enumerate(seed.questions):
        existing = questions.find_by_prompt(subject_id, spec.prompt)
        if existing is None:
            question = questions.add_idempotent(
                subject_id,
                level=spec.level,
                prompt=spec.prompt,
                reference_answer=spec.answer,
                run_id=SEED_RUN_ID,
            )
            added += 1
        elif existing.status != "active":
            retired += 1
            continue
        elif (existing.level, existing.reference_answer, existing.rubric) == (
            spec.level,
            spec.answer,
            None,
        ):
            question = existing
        elif replace_changed:
            question = questions.replace(
                existing.id, level=spec.level, reference_answer=spec.answer, run_id=SEED_RUN_ID
            )
            replaced += 1
        else:
            line = seed.question_lines[index]
            changed.append(
                f"line {line}: questions.{index}: differs from the question already seeded "
                "(level or answer); run again with --replace-changed to retire the old one"
            )
            continue
        for title in spec.units:
            links.link_once(question.id, unit_ids[title])
    if changed:
        raise SeedError(changed)
    return Seeded(added, replaced, retired)


def run(session: Session, argv: Sequence[str]) -> int:
    """Run in `session`; the caller commits on 0. Returns the exit status."""
    args = _parser().parse_args(argv)
    user = UserRepository(session).get_by_email(args.user_email)
    if user is None:
        print(f"no user with email {args.user_email}", file=sys.stderr)
        return 1
    try:
        seed = parse(Path(args.file).read_text(encoding="utf-8"))
    except OSError as error:
        print(f"cannot read {args.file}: {error.strerror}", file=sys.stderr)
        return 1
    except SeedFileError as error:
        for problem in error.problems:
            print(f"{args.file}: {problem}", file=sys.stderr)
        return 1
    try:
        with session.begin_nested():
            done = apply(session, user.id, args.subject, seed, replace_changed=args.replace_changed)
    except SubjectNotFoundError:
        print("no such subject for this user (or it was deleted)", file=sys.stderr)
        return 1
    except SeedError as error:
        for problem in error.problems:
            print(f"{args.file}: {problem}", file=sys.stderr)
        return 1
    print(
        f"added {done.added} questions, replaced {done.replaced}, "
        f"{len(seed.questions) - done.added - done.replaced - done.retired} were already there"
    )
    if done.retired:
        print(f"{done.retired} questions are retired (dropped): left as they are")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    with Session(get_engine()) as session:
        status = run(session, sys.argv[1:] if argv is None else argv)
        if status == 0:
            session.commit()
        return status


if __name__ == "__main__":
    sys.exit(main())
