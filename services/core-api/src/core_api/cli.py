"""Operator commands: `python -m core_api.cli <command> …` (T2.6).

rebuild-memory-state --user-email EMAIL
    Rebuild one user's memory_state from review_log (layer 4 is a cache of layer 3).
rebuild-practice-state --user-email EMAIL
    Rebuild one user's practice_state from practice_log (T8.3), keeping each removed_at.
seed-demo --user-email EMAIL
    Give one user a made-up subject to review by hand with the fake grader (T2.16, plan D-10).
    Local and test only.
"""

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy.orm import Session

from core_api.config import DEV_ENVIRONMENTS, get_settings
from core_api.db.engine import get_engine
from core_api.demo import DEMO_SUBJECT, seed_demo
from core_api.repositories.practice import PracticeStateRepository
from core_api.repositories.review import MemoryStateRepository
from core_api.repositories.user import UserRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m core_api.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    rebuild = commands.add_parser(
        "rebuild-memory-state", help="rebuild one user's memory_state from review_log"
    )
    rebuild.add_argument("--user-email", required=True)
    practice = commands.add_parser(
        "rebuild-practice-state", help="rebuild one user's practice_state from practice_log"
    )
    practice.add_argument("--user-email", required=True)
    demo = commands.add_parser("seed-demo", help="give one user a demo subject (local, test only)")
    demo.add_argument("--user-email", required=True)
    return parser


def run(session: Session, argv: Sequence[str], *, environment: str | None = None) -> int:
    """Run one command in `session`; the caller commits. Returns the exit status. `environment`
    is the settings' unless given (tests)."""
    args = _parser().parse_args(argv)
    if args.command == "seed-demo":
        environment = environment or get_settings().environment
        if environment not in DEV_ENVIRONMENTS:
            print("seed-demo runs only in local and test", file=sys.stderr)
            return 1
    user = UserRepository(session).get_by_email(args.user_email)
    if user is None:
        print(f"no user with email {args.user_email}", file=sys.stderr)
        return 1
    if args.command == "seed-demo":
        added = seed_demo(session, user)
        print(f"added {added} questions to {DEMO_SUBJECT}" if added else f"{DEMO_SUBJECT} is there")
        return 0
    if args.command == "rebuild-practice-state":
        rebuilt = PracticeStateRepository(session, user.id).rebuild()
        print(f"rebuilt {rebuilt} practice states")
        return 0
    written = MemoryStateRepository(session, user.id).rebuild()
    print(f"rebuilt {written} memory states")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    with Session(get_engine()) as session:
        status = run(session, sys.argv[1:] if argv is None else argv)
        if status == 0:
            session.commit()
        return status


if __name__ == "__main__":
    sys.exit(main())
