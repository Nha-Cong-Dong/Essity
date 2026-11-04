"""Operator commands: `python -m core_api.cli <command> …` (T2.6).

rebuild-memory-state --user-email EMAIL
    Rebuild one user's memory_state from review_log (layer 4 is a cache of layer 3).
rebuild-practice-state --user-email EMAIL
    Rebuild one user's practice_state from practice_log (T8.3), keeping each removed_at.
seed-demo --user-email EMAIL
    Give one user a made-up subject to review by hand with the fake grader (T2.16, plan D-10).
    Local and test only.
promote-drafts [--dry-run]
    Move every draft card still waiting for review into the vault (CARDS-V3): the same code a
    Save runs, so events, review questions and the ledger follow. Not reversible: back up first.
    Safe to run again.
erase-user --user-id UUID [--confirm-email EMAIL]
    Erase everything of one user (T6.3, runbook db-roles §4). Connects as the `core_eraser`
    login given in CORE_ERASER_DATABASE_URL, and as the app. The email is required while the
    user exists; omit it to run an erase again for a user that is gone. Safe to run again.
"""

import argparse
import os
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

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
    promote = commands.add_parser(
        "promote-drafts", help="move waiting draft cards into the vault (CARDS-V3)"
    )
    promote.add_argument("--dry-run", action="store_true")
    erase = commands.add_parser("erase-user", help="erase everything of one user (T6.3)")
    erase.add_argument("--user-id", required=True, type=uuid.UUID)
    erase.add_argument("--confirm-email")
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
    if args.command == "promote-drafts":
        from core_api.services.promote_drafts import promote_drafts

        report = promote_drafts(session, now=datetime.now(UTC), dry_run=args.dry_run)
        label = "would promote" if args.dry_run else "promoted"
        print(f"{label} {report.cards} cards of {report.sessions} sessions ({report.users} users)")
        return 0
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


def erase(argv: Sequence[str]) -> int:
    """`erase-user`: two connections and Redis and the store, so it does not take a session."""
    from core_api.clients.redis import get_redis
    from core_api.clients.storage import S3Storage
    from core_api.db.engine import create_db_engine
    from core_api.domain.delete_user import EraseRefused, erase_user

    args = _parser().parse_args(argv)
    url = os.environ.get("CORE_ERASER_DATABASE_URL")
    if not url:
        print("CORE_ERASER_DATABASE_URL is not set (see runbook db-roles §4)", file=sys.stderr)
        return 1
    eraser = create_db_engine(url, pool_size=1, max_overflow=0)
    try:
        result = erase_user(
            eraser_engine=eraser,
            app_engine=get_engine(),
            storage=S3Storage.from_settings(get_settings()),
            redis=get_redis(),
            user_id=args.user_id,
            now=datetime.now(UTC),
            confirm_email=args.confirm_email,
        )
    except EraseRefused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    except Exception as error:
        # The class only: a driver message can carry a host, a login or a statement (ADR-0013).
        print(
            f"erase stopped: {type(error).__name__}. Run the same command again to finish.",
            file=sys.stderr,
        )
        return 2
    finally:
        eraser.dispose()
    print(
        f"erased: user row {'deleted' if result.user_existed else 'already gone'}, "
        f"{result.outbox_rows} outbox rows, {result.objects} objects, "
        f"{result.dead_entries + result.stream_entries} stream entries; "
        "a second pass is queued for 20 minutes from now"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments[:1] == ["erase-user"]:
        return erase(arguments)
    with Session(get_engine()) as session:
        status = run(session, arguments)
        if status == 0:
            session.commit()
        return status


if __name__ == "__main__":
    sys.exit(main())
