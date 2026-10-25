"""Operator commands: `python -m core_api.cli <command> …` (T2.6).

rebuild-memory-state --user-email EMAIL
    Rebuild one user's memory_state from review_log (layer 4 is a cache of layer 3).
"""

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy.orm import Session

from core_api.db.engine import get_engine
from core_api.repositories.review import MemoryStateRepository
from core_api.repositories.user import UserRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m core_api.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    rebuild = commands.add_parser(
        "rebuild-memory-state", help="rebuild one user's memory_state from review_log"
    )
    rebuild.add_argument("--user-email", required=True)
    return parser


def run(session: Session, argv: Sequence[str]) -> int:
    """Run one command in `session`; the caller commits. Returns the exit status."""
    args = _parser().parse_args(argv)
    user = UserRepository(session).get_by_email(args.user_email)
    if user is None:
        print(f"no user with email {args.user_email}", file=sys.stderr)
        return 1
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
